# Data Sources Documentation

## Overview

This document describes the data sources used in the AI Supply Chain Trading system, including stock price data and financial news data.

---

## Stock Price Data

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
  data_dir: "C:/Users/dusro/Downloads/stock/stock_market_data"
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
  - `Volume` or `volume` (trading volume, optional but recommended)

### Date Range
- **Default:** 2020-01-01 to 2024-12-31
- Configurable in `config/data_config.yaml`

### Validation
The `UniverseLoader` validates price data based on:
- Minimum data points (default: 100 trading days)
- Date range coverage
- Missing days ratio (max 10%)
- Minimum price (exclude penny stocks < $1.00)

---

## Financial News Data: FNSPID Dataset

### Source
**FNSPID (Financial News Sentiment and Price Impact Dataset)**

- **Repository:** [Zihan1004/FNSPID](https://huggingface.co/datasets/Zihan1004/FNSPID) on Hugging Face
- **File:** `Stock_news/nasdaq_exteral_data.csv`
- **License:** Check Hugging Face repository for license details
- **Version:** Latest available on Hugging Face

### Dataset Details

**Coverage:**
- **Exchange:** NASDAQ
- **Date Range:** Varies (typically 2010-2022)
- **Article Count:** ~15 million articles (estimated)
- **Format:** CSV with columns including:
  - `headline` or `title`
  - `date` or `publishedAt`
  - `summary` or `description`
  - `content` or `text`
  - `ticker` or `symbol` (may need extraction)

**Fields:**
- Headline/Title: Article headline
- Date: Publication date
- Summary/Description: Article summary
- Content/Text: Full article text
- Ticker: Stock symbol (may be in headline or separate column)

### Download Instructions

**Step 1: Install Dependencies**
```bash
pip install huggingface_hub pandas pyarrow
```

**Step 2: Get Hugging Face Token**
1. Visit: https://huggingface.co/settings/tokens
2. Create a "Read" token (free)
3. Set environment variable:
   ```bash
   export HF_TOKEN=your_token_here
   ```

**Step 3: Download Dataset**
```bash
# With environment variable (recommended)
export HF_TOKEN=your_token_here
python scripts/download_fnspid.py

# Or with command-line argument
python scripts/download_fnspid.py --token your_token_here
```

This will:
- Download from Hugging Face with caching
- Save to `data/raw/fnspid_nasdaq_news.csv`
- Verify download and show statistics

**Step 3: Process Dataset**
```bash
python scripts/process_fnspid.py \
  --input data/raw/fnspid_nasdaq_news.csv \
  --output data/news/ \
  --date-start 2020-01-01 \
  --date-end 2022-12-31
```

This will:
- Filter by date range (2020-2022)
- Filter by supply chain keywords (90% reduction)
- Extract ticker symbols
- Convert to our JSON format
- Save to `data/news/{TICKER}_news.json`

### Filtering Criteria

**Keyword Filtering:**
Articles are filtered to include only those mentioning supply chain keywords:
- Supply chain terms: `supply`, `supplier`, `contract`, `partnership`, `partner`
- Infrastructure: `datacenter`, `data center`, `cloud`, `hyperscaler`
- AI/Technology: `AI`, `artificial intelligence`, `GPU`, `CPU`, `chip`, `semiconductor`
- Companies: `AWS`, `Azure`, `GCP`, `Microsoft`, `Google`, `Amazon`, `NVIDIA`, `AMD`, `Intel`, `TSMC`
- Other: `manufacturing`, `order`, `infrastructure`, `server`

**Why Filter?**
- Reduces dataset from ~15M to ~1.5M articles (90% reduction)
- Focuses on relevant supply chain news
- Reduces Gemini API calls (cost and time)
- Improves signal quality

**Date Filtering:**
- Default: 2020-01-01 to 2022-12-31
- Matches available price data range
- Configurable via `--date-start` and `--date-end` arguments

**Ticker Filtering:**
- By default, only processes tickers in our universe
- Use `--no-filter-universe` to process all tickers
- Ensures news data aligns with price data

### Output Format

**File Structure:**
```
data/news/
  ├── NVDA_news.json
  ├── AMD_news.json
  ├── QLYS_news.json
  └── ...
```

**JSON Format:**
```json
[
  {
    "title": "NVIDIA Announces Record GPU Orders",
    "description": "NVIDIA reports unprecedented demand...",
    "content": "NVIDIA Corporation announced today...",
    "publishedAt": "2023-06-15T10:00:00Z"
  },
  {
    "title": "...",
    "description": "...",
    "content": "...",
    "publishedAt": "2023-06-14T14:30:00Z"
  }
]
```

**Note:** Articles are sorted by date (newest first).

### Processing Statistics

After processing, you'll see:
- Total articles downloaded
- Articles after keyword filtering
- Tickers with news coverage
- Total articles saved
- Average articles per ticker
- Top 10 tickers by article count

**Example Output:**
```
PROCESSING SUMMARY
============================================================
Total articles downloaded: 15,234,567
Articles after keyword filtering: 1,523,456
Tickers with news coverage: 234
Total articles saved: 1,523,456
Average articles per ticker: 6,510.5

Top 10 tickers by article count:
  NVDA: 45,234 articles
  AMD: 32,156 articles
  INTC: 28,934 articles
  ...
```

---

## News Coverage Statistics

### Expected Coverage

**After Processing:**
- **Tickers with News:** ~200-300 (depends on universe)
- **Articles per Ticker:** 1,000-50,000 (varies by ticker)
- **Date Coverage:** 2020-2022 (3 years)
- **Keyword Match Rate:** ~10% (90% filtered out)

### Known Limitations

1. **Date Range:**
   - FNSPID dataset may not cover all dates
   - Some tickers may have gaps in coverage
   - News may be sparse for smaller companies

2. **Ticker Extraction:**
   - Ticker symbols may need to be extracted from headlines
   - Some articles may not have clear ticker association
   - Extraction may miss some valid articles

3. **Keyword Filtering:**
   - May miss relevant articles that don't use keywords
   - May include irrelevant articles that mention keywords
   - Filtering is case-insensitive but may have edge cases

4. **Data Quality:**
   - Some articles may have missing fields
   - Date parsing may fail for unusual formats
   - Content may be truncated or incomplete

5. **API Costs:**
   - Gemini API has rate limits and costs
   - Large datasets require many API calls
   - Consider caching results

---

## Alternative News Sources

### Polygon.io
- **API:** REST API with free tier
- **Coverage:** Real-time and historical
- **Format:** JSON API responses
- **Integration:** See `src/data/news_sources/polygon_source.py`

### MarketAux
- **API:** REST API with free tier
- **Coverage:** Financial news
- **Format:** JSON API responses
- **Integration:** See `src/data/news_sources/marketaux_source.py`

### Custom Sources
- Add new sources by implementing `NewsDataSource` interface
- See `src/data/news_base.py` for base class
- Register in `src/data/news_fetcher_factory.py`

---

## Verification

### Test Gemini Integration

After processing, verify Gemini is working:

```bash
export GEMINI_API_KEY=your_key_here
python scripts/test_gemini.py
```

This will:
- Test Gemini API connection
- Analyze sample articles
- Verify scores are NOT fallback values
- Check NewsAnalyzer integration

### Expected Test Output

**Success:**
```
[SUCCESS] All Gemini tests passed!
  Supply Chain Score: 0.850 (outside fallback range)
  Sentiment Score: 0.700 (outside fallback range)
```

**Fallback (No Real Analysis):**
```
[WARNING] Scores look like fallback values!
  Fallback range: supply_chain [0.3, 0.7], sentiment [-0.2, 0.2]
```

---

## Troubleshooting

### Download Issues

**Problem:** Download fails or is slow
- **Solution:** Check internet connection, try again (resume supported)
- **Alternative:** Download manually from Hugging Face website

**Problem:** File not found on Hugging Face
- **Solution:** Verify repository exists: https://huggingface.co/datasets/Zihan1004/FNSPID
- **Alternative:** Check if file path changed

### Processing Issues

**Problem:** No articles after filtering
- **Solution:** Check date range matches data
- **Solution:** Verify keyword filtering isn't too strict
- **Solution:** Check ticker extraction logic

**Problem:** Ticker extraction fails
- **Solution:** Check CSV column names
- **Solution:** Verify ticker format in headlines
- **Solution:** Use `--no-filter-universe` to see all tickers

### Gemini API Issues

**Problem:** All scores are fallback values
- **Solution:** Check `GEMINI_API_KEY` is set
- **Solution:** Verify API quota not exceeded
- **Solution:** Check news files exist and are valid JSON
- **Solution:** Run `test_gemini.py` to diagnose

**Problem:** API rate limits
- **Solution:** Add delays between calls
- **Solution:** Use batch processing
- **Solution:** Cache results to avoid re-analysis

---

## Data Updates

### Updating Price Data
1. Download new CSV files to data directory
2. Update `config/data_config.yaml` if needed
3. Run backtest to use new data

### Updating News Data
1. Re-download FNSPID dataset (if updated)
2. Re-run `process_fnspid.py` with new date range
3. News files will be overwritten/updated

### Incremental Updates
- News files can be appended (add new articles to existing JSON)
- Price data should replace old files
- Consider versioning for reproducibility

---

## License and Attribution

### FNSPID Dataset
- **License:** Check Hugging Face repository
- **Attribution:** Cite original paper/dataset if publishing
- **Usage:** Follow dataset license terms

### Stock Price Data
- **Source:** Multiple sources (NASDAQ, S&P 500, etc.)
- **License:** Check individual source licenses
- **Usage:** Typically free for research/personal use

---

## Summary

1. **Price Data:** CSV files in `data/prices/` or configured directory
2. **News Data:** FNSPID dataset processed to `data/news/{TICKER}_news.json`
3. **Download:** `python scripts/download_fnspid.py`
4. **Process:** `python scripts/process_fnspid.py`
5. **Verify:** `python scripts/test_gemini.py`
6. **Coverage:** ~200-300 tickers, 2020-2022, ~1.5M articles after filtering

For questions or issues, check:
- `scripts/download_fnspid.py` for download problems
- `scripts/process_fnspid.py` for processing problems
- `scripts/test_gemini.py` for Gemini integration problems
