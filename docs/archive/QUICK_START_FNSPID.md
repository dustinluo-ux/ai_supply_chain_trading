# Quick Start: FNSPID Dataset Integration

This guide walks you through downloading and processing the FNSPID dataset to enable real Gemini news analysis.

## Prerequisites

1. **Install Dependencies:**
```bash
pip install huggingface_hub pandas pyarrow
```

2. **Get Hugging Face Token:**
   - Visit: https://huggingface.co/settings/tokens
   - Create a "Read" token (free)
   - Set environment variable:
   ```bash
   export HF_TOKEN=your_token_here
   ```
   Or pass as argument: `--token your_token_here`

3. **Get Gemini API Key:**
   - Visit: https://aistudio.google.com/app/apikey
   - Create a free API key
   - Set environment variable:
   ```bash
   export GEMINI_API_KEY=your_key_here
   ```
   Or add to `.env` file:
   ```
   GEMINI_API_KEY=your_key_here
   ```

## Step-by-Step Instructions

### Step 1: Download FNSPID Dataset

**Default: Downloads to project folder (self-contained)**

```bash
python scripts/download_fnspid.py
```

This downloads the 23.2GB file directly to `data/raw/fnspid_nasdaq_news.csv` in your project folder, making it self-contained.

**Alternative: Use cache (saves disk space but not self-contained)**
```bash
python scripts/download_fnspid.py --use-cache
```

**If file is already in cache, move it to project folder:**
```bash
python scripts/move_cache_to_project.py
```

**Expected Output:**
```
============================================================
FNSPID Dataset Download
============================================================

[1/3] Downloading from Hugging Face...
  Repository: Zihan1004/FNSPID
  File: Stock_news/nasdaq_exteral_data.csv
  Output: data/raw/fnspid_nasdaq_news.csv
  [OK] Downloaded to cache: ...
  [OK] Saved to: data/raw/fnspid_nasdaq_news.csv

[2/3] Copying to output location...
  [OK] Saved to: data/raw/fnspid_nasdaq_news.csv

[3/3] Verifying download...
  [OK] File is valid CSV
  Columns (8):
    - headline: object
    - date: object
    - ...
  Total articles: 15,234,567
```

**Time:** ~5-30 minutes (depends on internet speed)

### Step 2: Process Dataset

```bash
python scripts/process_fnspid.py \
  --input data/raw/fnspid_nasdaq_news.csv \
  --output data/news/ \
  --date-start 2020-01-01 \
  --date-end 2022-12-31
```

**Expected Output:**
```
============================================================
FNSPID Dataset Processing
============================================================

[1/6] Loading universe tickers...
  [OK] Loaded 234 tickers from universe

[2/6] Filtering by keywords...
  Articles before filtering: 15,234,567
  Articles after filtering: 1,523,456
  Reduction: 90.0%

[3/6] Loading FNSPID data...
  [OK] Loaded 15,234,567 total articles

[4/6] Filtering by date range (2020-01-01 to 2022-12-31)...
  [OK] Filtered to 1,234,567 articles in date range

[5/6] Grouping articles by ticker...
  [OK] Found articles for 234 tickers

[6/6] Saving to JSON files in data/news...
  [OK] Saved 1,234,567 articles to 234 JSON files

============================================================
PROCESSING SUMMARY
============================================================
Total articles downloaded: 15,234,567
Articles after keyword filtering: 1,523,456
Tickers with news coverage: 234
Total articles saved: 1,234,567
Average articles per ticker: 5,275.9

Top 10 tickers by article count:
  NVDA: 45,234 articles
  AMD: 32,156 articles
  ...
```

**Time:** ~10-30 minutes (depends on file size and CPU)

### Step 3: Test Gemini Integration

```bash
export GEMINI_API_KEY=your_key_here
python scripts/test_gemini.py
```

**Expected Output (Success):**
```
============================================================
Direct Gemini API Test
============================================================

[OK] GEMINI_API_KEY found (length: 39)

[1/3] Testing GeminiAnalyzer initialization...
  [OK] GeminiAnalyzer initialized

[2/3] Analyzing test article...
  Title: NVIDIA Announces Record GPU Orders from Hyperscalers
  [OK] Analysis complete

  Results:
    Supplier: NVIDIA
    Customer Type: hyperscaler
    Product: GPUs
    AI Related: true
    Sentiment: positive
    Relevance Score: 0.95

  [OK] Relevance score > 0.5 (looks like real analysis)

[3/3] Testing NewsAnalyzer integration...
  Found news file: data/news/NVDA_news.json
  Testing analyze_news_for_ticker('NVDA', '2023-06-08', '2023-06-15')...

  News Analysis Results:
    Supply Chain Score: 0.850
    Sentiment Score: 0.700
    Confidence: 0.900

  [OK] Scores outside fallback range - likely real Gemini analysis!

============================================================
[SUCCESS] All Gemini tests passed!
============================================================
```

**Expected Output (Fallback - No Real Analysis):**
```
[WARNING] Scores look like fallback values!
  Fallback range: supply_chain [0.3, 0.7], sentiment [-0.2, 0.2]
  This may indicate:
    1. No articles found in date range
    2. Gemini API call failed
    3. News file format incorrect
```

### Step 4: Run Backtest with Real News

```bash
python test_signals.py --universe-size 10
```

**Expected Output:**
```
[NEWS DEBUG] NVDA: Loaded 5 articles from 2023-06-08 to 2023-06-15
[NEWS DEBUG] NVDA: Calling Gemini API with 5 articles...
[NEWS DEBUG] NVDA: Gemini returned: supply_chain=0.850, sentiment=0.700, confidence=0.900
```

**Not Fallback:**
```
[NEWS DEBUG] NVDA: Using fallback scores (no articles): supply_chain=0.523, sentiment=0.142
```

## Verification Checklist

- [ ] FNSPID dataset downloaded (`data/raw/fnspid_nasdaq_news.csv` exists)
- [ ] News files created (`data/news/NVDA_news.json` exists for test ticker)
- [ ] Gemini API key set (`GEMINI_API_KEY` environment variable)
- [ ] Gemini test passes (scores outside fallback range)
- [ ] Backtest shows real news analysis (not fallback)

## Troubleshooting

### Download Issues

**Problem:** `huggingface_hub` not found
```bash
pip install huggingface_hub pandas pyarrow
```

**Problem:** Download fails or is slow
- Check internet connection
- Try again (resume supported)
- Download manually from Hugging Face website

### Processing Issues

**Problem:** No articles after filtering
- Check date range matches data
- Verify keyword filtering isn't too strict
- Check ticker extraction logic

**Problem:** Ticker extraction fails
- Check CSV column names
- Verify ticker format in headlines
- Use `--no-filter-universe` to see all tickers

### Gemini API Issues

**Problem:** `GEMINI_API_KEY` not set
```bash
export GEMINI_API_KEY=your_key_here
```

**Problem:** All scores are fallback values
- Check `GEMINI_API_KEY` is set correctly
- Verify API quota not exceeded
- Check news files exist and are valid JSON
- Run `test_gemini.py` to diagnose

**Problem:** API rate limits
- Add delays between calls
- Use batch processing
- Cache results to avoid re-analysis

## Next Steps

1. **Optimize Weights:** Test different signal weight combinations
2. **Expand Coverage:** Process more tickers or date ranges
3. **Add Sources:** Integrate additional news sources (Polygon, MarketAux)
4. **Cache Results:** Cache Gemini analysis to reduce API calls

## Documentation

- **Data Sources:** `docs/DATA_SOURCES.md`
- **News Analysis:** `docs/NEWS_ANALYSIS_EXPLAINED.md`
- **Trading Strategy:** `docs/TRADING_STRATEGY_EXPLAINED.md`

## Support

For issues or questions:
1. Check `docs/DATA_SOURCES.md` for detailed documentation
2. Run `scripts/test_gemini.py` to diagnose problems
3. Check debug output in backtest logs (`outputs/backtest_log_*.txt`)
