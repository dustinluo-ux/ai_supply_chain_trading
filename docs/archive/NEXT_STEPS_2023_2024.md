# Next Steps: Using 2023-2024 News Data

## ✅ Completed

1. **CSV Slicing**: Extracted 2023-2024 data from 21.64 GB → 6.032 GB
   - File: `data/raw/fnspid_nasdaq_news_2023_2024.csv`
   
2. **Data Processing**: Converted CSV to JSON format
   - **3,701 ticker files** created in `data/news/`
   - Files: `{TICKER}_news.json` (e.g., `NVDA_news.json`, `AAPL_news.json`)
   - Filtered by supply chain keywords
   - Date range: 2023-01-01 to 2024-12-31

3. **Configuration Updated**: 
   - `config/data_config.yaml` now uses 2023-2024 date range

## 🚀 Next Steps

### Step 1: Test Gemini Integration

Verify that Gemini API is working with your news data:

```bash
python scripts/test_gemini.py
```

**Expected Output:**
- ✅ GeminiAnalyzer initialized
- ✅ Real analysis scores (not fallback values)
- ✅ Supply chain and sentiment scores

**If you need to set API key:**
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your_key_here"

# Or add to .env file
GEMINI_API_KEY=your_key_here
```

### Step 2: Run Test Signals

Test the signal generation with a small universe:

```bash
python test_signals.py --universe-size 10
```

This will:
- Load 10 tickers
- Generate technical signals
- Analyze news using Gemini (if API key set)
- Show signal scores and backtest results

**Look for:**
- `[NEWS DEBUG]` messages showing real Gemini analysis
- Scores outside fallback range (0.3-0.7 for supply chain, -0.2-0.2 for sentiment)

### Step 3: Run Full Backtest

Run a complete backtest with the 2023-2024 data:

```bash
python test_signals.py --universe-size 50
```

Or use the phase-based approach:

```bash
python run_phase3_backtest.py
```

## 📊 What You Have Now

- **News Data**: 3,701 tickers with 2023-2024 news articles
- **Coverage**: Recent data (2023-2024) for better relevance
- **Format**: JSON files ready for Gemini analysis
- **Size**: 6.032 GB (much more manageable than 21.64 GB)

## 🔍 Verification

Check your news data:

```bash
# Count news files
python -c "from pathlib import Path; print(f'News files: {len(list(Path(\"data/news\").glob(\"*_news.json\")))}')"

# Check a specific ticker
python -c "import json; from pathlib import Path; f = Path('data/news/NVDA_news.json'); data = json.load(open(f)) if f.exists() else []; print(f'NVDA articles: {len(data)}')"
```

## 📝 Notes

- **Date Range**: News data is now 2023-2024 (updated from 2020-2022)
- **Stock Data**: Still needs to be moved to OneDrive (see `DATA_MANAGEMENT_GUIDE.md`)
- **Gemini API**: Required for real news analysis (free tier available)

## 🐛 Troubleshooting

**No news analysis:**
- Check `GEMINI_API_KEY` is set
- Verify news files exist: `data/news/{TICKER}_news.json`
- Run `python scripts/test_gemini.py` to diagnose

**Fallback scores:**
- Means Gemini API not working or no articles found
- Check API key and network connection
- Verify date range matches your backtest dates

**Missing tickers:**
- Some tickers may not have news data
- System will use fallback scores for those tickers
- This is normal - not all stocks have supply chain news

## 📚 Documentation

- **Quick Start**: `QUICK_START_FNSPID.md`
- **Data Management**: `DATA_MANAGEMENT_GUIDE.md`
- **News Analysis**: `docs/NEWS_ANALYSIS_EXPLAINED.md`
- **Trading Strategy**: `docs/TRADING_STRATEGY_EXPLAINED.md`
