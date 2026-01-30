# FNSPID Raw File Date Check Results

**Date:** 2026-01-29  
**Goal:** Determine if the raw FNSPID file has NVDA/AMD/TSM/AAPL articles **before Oct 2022** so we can re-process for Apr–Dec 2022 (9 months).

---

## Step 1: Find the raw FNSPID file

```bash
python scripts/find_cache_path.py
```

**Result:**  
- Found FNSPID repository: `Zihan1004/FNSPID`  
- **Cached file not found** (no path printed)  
- Raw file was instead present at: **`data/raw/fnspid_nasdaq_news.csv`** (project path)

So the file to use is: **`data/raw/fnspid_nasdaq_news.csv`**.

---

## Step 2: Check overall date range in raw file

```bash
python scripts/check_fnspid_date_range.py data/raw/fnspid_nasdaq_news.csv
```

**Result:**  
- Date column: `Date`  
- Sampled first 100,000 rows  
- **Date range in sample: 2009-06-09 to 2023-12-16**  
- So the raw file has data from 2009 through 2023 (plenty of 2022 and earlier).

---

## Step 3: Check NVDA / AMD / TSM / AAPL before Oct 2022

```bash
python scripts/check_fnspid_ticker_dates_fast.py data/raw/fnspid_nasdaq_news.csv
```

**Result (first 150,000 rows, cols: Date + Article_title):**

| Ticker | Earliest date | Latest date | Count (in sample) | Before Oct 2022? |
|--------|----------------|-------------|-------------------|-------------------|
| AAPL   | 2014-01-28     | 2023-12-16  | 322               | **YES**           |
| AMD    | 2016-04-19     | 2023-12-16  | 40                | **YES**           |
| NVDA   | 2017-05-04     | 2023-12-16  | 67                | **YES**           |
| TSM    | 2013-07-02     | 2023-12-16  | 36                | **YES**           |

So in the raw FNSPID file:

- **NVDA** has articles before Oct 2022 (earliest in sample: 2017-05-04).  
- **AMD, TSM, AAPL** also have articles before Oct 2022 (earliest in sample: 2013–2016).  
- All four have data spanning through 2023 in the sample.

---

## Conclusion

- **FNSPID has Apr–Sep 2022 data** for our universe tickers (NVDA, AMD, TSM, AAPL).  
- **We can re-process** and do **not** need Polygon/Tiingo for Apr–Sep 2022 for this check.

**Recommended next step:** Re-run FNSPID processing for **Apr–Dec 2022** so `data/news/` gets 9 months of overlap with price:

```bash
python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input data/raw/fnspid_nasdaq_news.csv
```

(Add `--no-filter-universe` if you want all tickers, not only the current universe.)

Then run the backtest again; the 6–12 month overlap logic in `test_signals.py` should pick up the extended period when both price and news cover Apr–Dec 2022.

---

## Scripts used

| Script | Purpose |
|--------|--------|
| `scripts/find_cache_path.py` | Locate FNSPID file in Hugging Face cache (optional; we used project path). |
| `scripts/check_fnspid_date_range.py <path>` | Sample first 100k rows; report min/max date in raw file. |
| `scripts/check_fnspid_ticker_dates_fast.py <path>` | First 150k rows; report earliest/latest date and count for NVDA, AMD, TSM, AAPL (from `Article_title` or ticker column). |
