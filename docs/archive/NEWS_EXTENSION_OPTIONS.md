# News Extension Options: Getting 6–12 Months for Backtest

**Goal:** Overlap price + news for at least 6 months (e.g. Apr–Dec 2022) for a statistically valid backtest.  
**Current:** Only 2.3 months overlap (Oct–Dec 2022) because **key universe tickers** (NVDA, TSM, AMD, AAPL, etc.) have news only from Oct/Nov 2022 in `data/news/`.

---

## 1. What News We Currently Have

**Source:** Full scan of `data/news/*.json` via `scripts/news_date_range_report.py`.

### Overall

- **Tickers with news:** 3,720  
- **Overall date range:** 2021-01-02 to 2024-05-05  
- **But** supply-chain universe tickers have much narrower ranges (see below).

### Date range for key universe tickers (supply chain top)

| Ticker | Start      | End        | Articles |
|--------|------------|------------|----------|
| NVDA   | 2022-10-02 | 2022-12-31 | 464      |
| TSM    | 2022-10-02 | 2022-12-31 | 244      |
| AMD    | 2022-10-03 | 2022-12-31 | 382      |
| AMAT   | 2022-11-01 | 2022-11-30 | 32       |
| INTC   | 2022-11-01 | 2022-11-30 | 87       |
| AAPL   | 2022-10-01 | 2022-12-31 | 1,293    |
| MSFT   | 2022-11-01 | 2022-11-30 | 278      |
| MU     | 2022-11-01 | 2022-11-30 | 44       |
| QCOM   | 2022-10-02 | 2022-12-30 | 151      |

So **all** of these have news only from **Oct or Nov 2022** → backtest overlap is ~2.3 months.

### Article count by month (all tickers)

- **2022-01 to 2022-09:** 53–298 articles/month, **~39–45 tickers** (other tickers, e.g. BA, CHDN, GBCI).  
- **2022-10 to 2022-12:** 8,852–12,275 articles/month, **607–894 tickers** (includes NVDA, AAPL, etc.).

So we **do** have Jan–Sep 2022 articles in `data/news/`, but for **different** tickers (not the current supply-chain universe). That suggests either:

1. FNSPID was run with a **narrower date window** (e.g. `--date-start 2022-10-01`) so NVDA/AAPL etc only got Oct–Dec, or  
2. The **raw FNSPID** file only has NASDAQ coverage for names like NVDA/AAPL from Oct 2022 onward.

**Conclusion:** To get 6+ months for **our universe** we need either to re-process FNSPID for Apr–Dec 2022 (if the raw file has those dates for our tickers) or to add another source for Apr–Sep 2022.

---

## 2. Does FNSPID Have More Data We Didn’t Process?

- **Script:** `scripts/process_fnspid.py`  
  - Defaults: `date_start='2020-01-01'`, `date_end='2022-12-31'`.  
  - So by default it **would** include Apr–Dec 2022; the current JSON files for NVDA/AAPL etc looking like “Oct–Dec only” imply either a run with a later `--date-start` or that the **raw FNSPID** has those tickers only in Oct–Dec 2022.

- **Check raw FNSPID date range (no full load):**  
  `python scripts/check_fnspid_date_range.py [path_to_fnspid.csv]`  
  - Default path: `data/raw/fnspid_nasdaq_news.csv`.  
  - If the file is in Hugging Face cache, run `python scripts/find_cache_path.py` and pass the printed path to `check_fnspid_date_range.py`.  
  - The script samples the first 100k rows and reports the date range in that sample. If the file is chronological, that approximates the start of the dataset.

- **If the raw file has dates before Oct 2022:**  
  Re-run processing with an earlier start so we explicitly pull Apr–Dec 2022 (see below).

---

## 3. Best Way to Get Apr–Dec 2022 (9 Months)

### Option 1: FNSPID extension (recommended first step)

Re-process FNSPID for **Apr–Dec 2022** so that, if the raw file has our tickers in that range, we get 9 months in `data/news/`.

1. **Locate raw FNSPID CSV**  
   - Project: `data/raw/fnspid_nasdaq_news.csv`, or  
   - Cache: `python scripts/find_cache_path.py` and use the path it prints.

2. **Optional: check raw date range**  
   ```bash
   python scripts/check_fnspid_date_range.py [path_to_fnspid.csv]
   ```  
   If the sample shows dates in Apr 2022 or earlier, proceeding makes sense.

3. **Re-run processing for Apr–Dec 2022**  
   ```bash
   python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input <path_to_fnspid.csv>
   ```  
   - Default `--input` is `data/raw/fnspid_nasdaq_news.csv` if the file is there.  
   - This **overwrites** existing `data/news/<TICKER>_news.json` for tickers that get new articles; articles are appended/merged per ticker by the script’s grouping, so you get **all** articles in the chosen range (Apr–Dec 2022).  
   - If you previously processed only Oct–Dec 2022, run once with `--date-start 2022-04-01` and you will get Apr–Dec in one go.  
   - To process **all** tickers (not only current universe), add `--no-filter-universe`.

4. **Re-check news range**  
   ```bash
   python scripts/news_date_range_report.py
   ```  
   Confirm that NVDA, AMD, TSM, AAPL, etc. now show start dates in Apr 2022 (or earlier) if the raw file contained them.

**If the raw FNSPID does *not* have our universe tickers before Oct 2022,** Option 2 is needed for Apr–Sep 2022.

---

### Option 2: Alternative news source (Apr–Sep 2022)

Use a second source for historical news for the same universe:

- **Polygon.io**  
  - Historical news API (free tier often includes ~2 years).  
  - Existing script: `process_polygon_news.py` (root).  
  - Download and normalize to the same JSON shape as FNSPID (`title`, `publishedAt`, etc.) and either merge into `data/news/<TICKER>_news.json` or write to a separate folder and adapt the backtest to read both.

- **Tiingo**  
  - News API; check whether the plan allows historical range for 2022.  
  - Fetch for universe tickers for 2022-04-01 to 2022-09-30, then convert to the same format and merge into `data/news/` (or a dedicated directory).

- **Merge strategy**  
  - Same format as current: one JSON per ticker, list of articles with `publishedAt`.  
  - Merge by ticker: load existing `data/news/<TICKER>_news.json`, append new articles, sort by date, dedupe by URL or title+date, write back.

---

### Option 3: Relax date filtering (only if appropriate)

- **Backtest:** The 6–12 month window is already the overlap of **price** and **news**; we don’t tighten dates further there.  
- **process_fnspid:** Uses `date_start` / `date_end` only to filter the raw CSV. Using `--date-start 2022-04-01` is the right way to “extend” to Apr–Dec 2022; we are not over-filtering by date in the script.  
- So “date filtering too strict” is not the issue; the limitation is **what’s in the current JSON files** (and possibly in the raw FNSPID) for our universe.

---

## 4. Summary

| Question | Answer |
|----------|--------|
| **What news do we have?** | 3,720 tickers; overall 2021–2024. **Key universe tickers (NVDA, TSM, AMD, AAPL, etc.) only Oct–Dec 2022** in `data/news/`. Jan–Sep 2022 exists for other tickers. |
| **Does FNSPID have more we didn’t process?** | Unknown until we check the raw file. Run `scripts/check_fnspid_date_range.py` on the raw CSV (or cache path). `process_fnspid` defaults to 2020–2022, so if the raw file has Apr–Dec 2022 for our tickers, we didn’t necessarily process it (e.g. if a past run used `--date-start 2022-10-01`). |
| **Best way to get Apr–Dec 2022?** | **(1)** Re-run `process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31`; then re-run `news_date_range_report.py` to confirm. **(2)** If the raw FNSPID doesn’t have our tickers before Oct 2022, use Polygon or Tiingo for Apr–Sep 2022 and merge into `data/news/` in the same format. |

---

## 5. Scripts Reference

| Script | Purpose |
|--------|--------|
| `scripts/news_date_range_report.py` | Scan all `data/news/*.json`; print date range per ticker, article count by month, and tickers with Apr 2022. |
| `scripts/check_fnspid_date_range.py [path]` | Sample raw FNSPID CSV date column; report min/max (no full load). |
| `scripts/find_cache_path.py` | Find cached FNSPID file path (e.g. Hugging Face). |
| `scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31` | Re-process FNSPID for Apr–Dec 2022 into `data/news/`. |

After extending news to Apr–Dec 2022 (or at least 6 months) for the backtest universe, re-run the backtest; the overlap logic in `test_signals.py` will then use 6–12 months when available.
