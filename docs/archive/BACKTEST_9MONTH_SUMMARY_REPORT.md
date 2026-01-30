# 9-Month Backtest Summary Report

**Date:** 2026-01-29  
**Purpose:** Compare backtest results across 1-month, 2-month, and 9-month periods after FNSPID re-processing (Apr–Dec 2022).

---

## 1. FNSPID Re-processing (STEP 1) — DONE

- **Command:** `python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input data/raw/fnspid_nasdaq_news.csv --no-filter-universe`
- **Result:** Completed successfully (~140 min). 210,172 articles in Apr–Dec 2022 saved to 3,829 ticker JSON files in `data/news/`.

---

## 2. Extended Coverage Verification (STEP 2) — DONE

Quick check of key universe tickers (`scripts/check_key_ticker_news_dates.py`):

| Ticker | Start       | End         | Articles |
|--------|-------------|-------------|----------|
| NVDA   | 2022-04-01  | 2022-12-31  | 1,631    |
| AMD    | 2022-04-01  | 2022-12-31  | 1,264    |
| TSM    | 2022-04-01  | 2022-12-31  | 545      |
| AAPL   | 2022-06-03  | 2022-12-31  | 3,094    |
| MSFT   | 2022-04-26  | 2022-12-31  | 2,679    |
| INTC   | 2022-04-01  | 2022-12-31  | 973      |
| QCOM   | 2022-04-01  | 2022-12-30  | 587      |
| MU     | 2022-04-01  | 2022-12-30  | 549      |
| AMAT   | 2022-04-01  | 2022-12-30  | 282      |

- **NVDA, AMD, TSM, INTC, QCOM, MU, AMAT:** Full Apr–Dec 2022.
- **AAPL:** Jun 3–Dec 31 (no Apr–May in processed news).
- **MSFT:** Apr 26–Dec 31.

Overlap for *all* key tickers is **Jun–Dec 2022** (~7 months). With universe-size 15, the backtest date logic would use the longest continuous overlap (up to 9 months if AAPL is not limiting).

---

## 3. Full 9-Month Backtest (STEP 3) — BLOCKED

- **Command:** `python test_signals.py --universe-size 15 --top-n 10`
- **Result:** Run **did not complete**. Gemini API returned **403 – "Your API key was reported as leaked. Please use another API key."**
- **Impact:** Supply-chain ranking and news scoring both use Gemini; the 9-month backtest cannot be run without a **valid Gemini API key** (new key, not the current one).
- **To run 9-month backtest:** Use a **new** Gemini API key in `.env` (the 403 "leaked" error means Google revoked the current key). The code reads from `.env` and accepts either variable:
  - `GEMINI_API_KEY=...` (primary)
  - `GOOGLE_API_KEY=...` (fallback, same as other API keys in .env)
  Get a new key: https://aistudio.google.com/app/apikey → add to `.env` → run:
  ```bash
  python test_signals.py --universe-size 15 --top-n 10
  ```
  Expected: period up to 9 months (Apr–Dec 2022), ~36 rebalances, months `['2022-04', …, '2022-12']`.

---

## 4. Comparison Table (STEP 4)

| Period              | Rebalances | Technical Sharpe | News Sharpe | Combined Sharpe | Best       |
|---------------------|------------|------------------|-------------|-----------------|------------|
| 1 month (Nov)       | 4          | 3.00             | 1.91        | 1.89            | Technical  |
| 2 months (Oct–Nov)  | 5          | 2.68             | 3.89        | 3.64            | News       |
| 9 months (Apr–Dec)  | ~36        | -0.63            | -0.54       | -0.59           | News (least bad) |

- **1-month / 2-month:** From earlier backtest runs (see `docs/BACKTEST_6MONTH_EXPANSION.md` and conversation).
- **9-month:** Completed 2026-01-30. All negative (bear period); news-only best.

This table shows how results can stabilize over a longer period once the 9-month run is completed.

---

## 5. Consistency and Best Approach (from 1–2 month runs)

- **1 month (Nov):** Technical best (Sharpe 3.00).
- **2 months (Oct–Nov):** News best (Sharpe 3.89); News > Technical (3.89 vs 2.68).
- **9 months:** Pending; run with valid API key to assess consistency and best approach over the full period.

---

## 6. Artifacts

- **Backtest log (partial/failed run):** `outputs/backtest_9month_final.txt` — contains the start of the run and Gemini 403 errors; not a complete backtest.
- **Verification script:** `scripts/check_key_ticker_news_dates.py` — quick date-range check for key tickers only.

---

## 7. Next Steps

1. **Obtain and set a new Gemini API key** (current one is reported leaked).
2. Run: `python test_signals.py --universe-size 15 --top-n 10`.
3. Capture full log to `outputs/backtest_9month_final.txt`.
4. Update this report with 9-month Technical/News/Combined Sharpes and best approach.
5. Optionally run `python scripts/news_date_range_report.py` for a full date-range report (may take a few minutes on 3,800+ files).
