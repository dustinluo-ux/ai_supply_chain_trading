# Data Management Guide

This guide explains how to manage large data files for this project, including slicing the 23GB news CSV and moving stock data to OneDrive.

## Overview

- **News Data**: 21.64 GB CSV file (`fnspid_nasdaq_news.csv`) containing millions of news articles
- **Stock Data**: 9.53 GB of historical stock price data currently on C drive

## Step 1: Slice News CSV for PoC (2023-2024)

The large 21.64 GB CSV file is being processed to extract only 2023-2024 data, reducing it to ~200-500MB.

### Status
✅ **Scripts Created:**
- `scripts/peek_csv_structure.py` - Inspect CSV structure
- `scripts/slice_csv_for_poc.py` - Extract 2023-2024 data

### CSV Structure Found
- **Date Column**: `Date`
- **Content Columns**: `Article`, `Article_title`, `Lsa_summary`, `Luhn_summary`, `Textrank_summary`, `Lexrank_summary`
- **Other Columns**: `Stock_symbol`, `Url`, `Publisher`, `Author`

### Running the Slice Script

The slice script is currently running in the background. To run it manually:

```bash
python scripts/slice_csv_for_poc.py --date-column Date
```

**Output**: `data/raw/fnspid_nasdaq_news_2023_2024.csv` (~200-500MB)

### Options
- `--input`: Input CSV path (default: `data/raw/fnspid_nasdaq_news.csv`)
- `--output`: Output CSV path (default: `data/raw/fnspid_nasdaq_news_2023_2024.csv`)
- `--date-start`: Start date (default: `2023-01-01`)
- `--date-end`: End date (default: `2024-12-31`)
- `--date-column`: Date column name (default: auto-detect)
- `--chunksize`: Rows per chunk (default: 100000)

## Step 2: Move Stock Data to OneDrive

Stock data is currently on C drive and should be moved to OneDrive for cloud storage.

### Current Location
- **Source**: `C:\Users\dusro\Downloads\stock\stock_market_data`
- **Size**: 9.53 GB
- **Subdirectories**:
  - `forbes2000`: 2.19 GB
  - `nasdaq`: 3.36 GB
  - `nyse`: 2.71 GB
  - `sp500`: 1.27 GB

### Destination
- **Target**: `C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\stock_market_data`

### Running the Move Script

**Dry Run** (see what would be moved):
```bash
python scripts/move_stock_data_to_onedrive.py --dry-run
```

**Actual Move** (moves files and deletes source):
```bash
python scripts/move_stock_data_to_onedrive.py
```

⚠️ **Warning**: The move script will delete files from the source after successful copy. Make sure you have backups if needed.

### After Moving

After moving the stock data, update `config/data_config.yaml`:

```yaml
data_sources:
  data_dir: "C:/Users/dusro/OneDrive/Programming/ai_supply_chain_trading/data/stock_market_data"
```

## Step 3: Update Configuration

After moving stock data, update the configuration file:

1. Open `config/data_config.yaml`
2. Update `data_dir` to point to the new OneDrive location
3. Save the file

The config has already been prepared with the new path - just uncomment or update it after the move.

## File Sizes Summary

| Data Type | Current Size | Location | Target Size | Target Location |
|-----------|-------------|----------|-------------|-----------------|
| News CSV (Full) | 21.64 GB | `data/raw/fnspid_nasdaq_news.csv` | Keep as archive | Same |
| News CSV (PoC) | ~200-500 MB | `data/raw/fnspid_nasdaq_news_2023_2024.csv` | Ready to use | Same |
| Stock Data | 9.53 GB | `C:\Users\dusro\Downloads\stock\...` | 9.53 GB | OneDrive |

## Next Steps

1. ✅ **CSV Slicing**: Running in background - check `data/raw/fnspid_nasdaq_news_2023_2024.csv` when complete
2. ⏳ **Move Stock Data**: Run `python scripts/move_stock_data_to_onedrive.py` when ready
3. ⏳ **Update Config**: Update `data_config.yaml` after moving stock data
4. ✅ **Test**: Verify data loading works with new paths

## Troubleshooting

### CSV Slice Script Issues
- **Date parsing errors**: Check date format in CSV, may need to specify `--date-column` manually
- **Memory issues**: Reduce `--chunksize` (default: 100000)
- **No matching rows**: Check date range - data may not include 2023-2024

### Move Script Issues
- **Permission errors**: Run as administrator or check file permissions
- **Disk space**: Ensure OneDrive has enough space (9.53 GB + overhead)
- **OneDrive sync**: Large files may take time to sync to cloud

### Configuration Issues
- **Path format**: Use forward slashes `/` or raw strings `r"C:\path"` in YAML
- **Relative paths**: Use absolute paths for reliability
- **Case sensitivity**: Windows paths are case-insensitive, but be consistent

## Scripts Reference

### `peek_csv_structure.py`
Inspect CSV file structure without loading entire file.

```bash
python scripts/peek_csv_structure.py [file_path]
```

### `slice_csv_for_poc.py`
Extract date range from large CSV file.

```bash
python scripts/slice_csv_for_poc.py [options]
```

### `move_stock_data_to_onedrive.py`
Move stock data from C drive to OneDrive.

```bash
python scripts/move_stock_data_to_onedrive.py [--dry-run] [--source PATH] [--dest PATH]
```
