# Scripts Directory

This directory contains utility scripts for downloading and processing data.

## FNSPID Dataset Pipeline

### 1. Download FNSPID Dataset

Download NASDAQ news data from Hugging Face:

```bash
# Default: Downloads to project folder (self-contained)
python scripts/download_fnspid.py

# Alternative: Use cache (saves space but not self-contained)
python scripts/download_fnspid.py --use-cache
```

**Note:** Default behavior downloads directly to `data/raw/fnspid_nasdaq_news.csv` in your project folder, making the project self-contained (all data in one place).

**Get Token:**
- Visit: https://huggingface.co/settings/tokens
- Create a "Read" token (free)

**Options:**
- `--output PATH`: Custom output path (default: `data/raw/fnspid_nasdaq_news.csv`)
- `--token TOKEN`: Hugging Face token (or set `HF_TOKEN` environment variable)

**Requirements:**
```bash
pip install huggingface_hub pandas pyarrow
```

**What it does:**
- Downloads `nasdaq_exteral_data.csv` from Hugging Face repository `Zihan1004/FNSPID`
- Saves to `data/raw/fnspid_nasdaq_news.csv`
- Verifies download and shows statistics

### 2. Process FNSPID Dataset

Filter and convert news data to our JSON format:

```bash
python scripts/process_fnspid.py \
  --input data/raw/fnspid_nasdaq_news.csv \
  --output data/news/ \
  --date-start 2020-01-01 \
  --date-end 2022-12-31
```

**Options:**
- `--input PATH`: Input CSV file (default: `data/raw/fnspid_nasdaq_news.csv`)
- `--output DIR`: Output directory (default: `data/news`)
- `--date-start DATE`: Start date filter (YYYY-MM-DD, default: 2020-01-01)
- `--date-end DATE`: End date filter (YYYY-MM-DD, default: 2022-12-31)
- `--no-filter-universe`: Process all tickers, not just universe tickers

**What it does:**
- Filters articles by date range (2020-2022)
- Filters by supply chain keywords (90% reduction)
- Extracts ticker symbols
- Converts to JSON format: `data/news/{TICKER}_news.json`
- Shows processing statistics

### 3. Test Gemini Integration

Verify Gemini API is working:

```bash
export GEMINI_API_KEY=your_key_here
python scripts/test_gemini.py
```

**What it does:**
- Tests Gemini API connection
- Analyzes sample articles
- Verifies scores are NOT fallback values
- Tests NewsAnalyzer integration

**Expected Output:**
- `[SUCCESS]` if Gemini is working
- `[WARNING]` if using fallback scores

## Quick Start

**Complete pipeline:**

```bash
# 1. Download dataset
python scripts/download_fnspid.py

# 2. Process dataset
python scripts/process_fnspid.py

# 3. Test Gemini (requires API key)
export GEMINI_API_KEY=your_key_here
python scripts/test_gemini.py

# 4. Run backtest with real news
python test_signals.py --universe-size 10
```

## Troubleshooting

### Download Fails
- Check internet connection
- Verify Hugging Face repository exists
- Try manual download from website

### Processing Fails
- Check CSV file exists and is valid
- Verify date range matches data
- Check ticker extraction logic

### Gemini Test Fails
- Verify `GEMINI_API_KEY` is set
- Check API quota not exceeded
- Verify news files exist

See `docs/DATA_SOURCES.md` for detailed documentation.
