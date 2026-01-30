# Backtest Expansion: 1 Month → 6+ Months

**Date:** 2026-01-29  
**Purpose:** Use 6–12 months of overlapping price + news for statistically significant backtest (24+ rebalances) and investor presentation.

---

## 1. What Was Implemented

In `test_signals.py`:

- **Constants:** `MIN_BACKTEST_MONTHS = 6`, `MAX_BACKTEST_MONTHS = 12`.
- **Date selection:** Replaced “best single month” with:
  1. **Overlap:** Union of news date ranges for universe tickers, intersected with price range.
  2. **Duration:** Use 6–12 months within that overlap (month-aligned); if overlap &lt; 6 months, use all available and warn.
- **Logging:** Script now prints:
  - Months in period (e.g. `['2022-10', '2022-11']`)
  - Expected rebalances (Mondays in period)
  - Expected Gemini API usage (1 ranking + weeks × tickers analyses, cached after first run)
- **Results:** Summary includes period length, rebalances, and “News vs technical” comparison.

---

## 2. First Run Results (5 tickers, 5 rebalances)

**Command:** `python test_signals.py --universe-size 5 --top-n 3`

**Why only 2 months?**  
Overlap of price and news for the 5 universe tickers (NVDA, TSM, AMD, AMAT, INTC) was **2.3 months** (2022-10-02 to 2022-12-12). So the logic correctly used “all available” and warned.

- **Months used:** `['2022-10', '2022-11']`
- **Rebalances:** 5 weekly rebalances (2022-10-31 to 2022-11-28)
- **Gemini:** 1 ranking run + up to 5×5 = 26 analyses (cached after first run)

**Sharpe ratios (full period):**

| Approach        | Sharpe | Return  | Max drawdown |
|----------------|--------|---------|--------------|
| technical_only | 2.68   | 11.36%  | -6.65%       |
| news_only     | **3.89** | 17.16% | -4.57%       |
| combined      | 3.64   | 16.25%  | -4.90%       |

**Best:** news_only (Sharpe 3.89).  
**News vs technical:** News matches or beats technical (3.89 vs 2.68) in this run.

**Runtime:** ~516 s (data load ~325 s, signals ~9.6 s, backtests ~0.4 s).

---

## 3. Consistency Across Months

- The backtest now uses **all weeks in the chosen period** (no longer limited to a single month).
- With **2 months** in this run, the Sharpes above are over Oct–Nov 2022 only.
- For **6+ months**, once your data overlap is at least 6 months, the same logic will use 6–12 months and ~24+ rebalances; then “consistency across months” can be checked over a longer window (e.g. per-month Sharpe in a future enhancement).

---

## 4. How to Get 6+ Months and 24+ Rebalances

Overlap is driven by:

- **Price range:** From loaded CSVs (e.g. 2022-01-03 to 2022-12-12).
- **News range:** Union of news dates for **universe tickers** (earliest article to latest).

To get 6+ months:

1. **Earlier news for universe tickers:** Ensure news data for NVDA, TSM, AMD, etc. goes back at least 6 months before the end of your price range (e.g. news from May 2022 if price ends Dec 2022).
2. **Or longer price range:** Use price data that extends further (e.g. into 2023) so overlap with existing news spans 6+ months.
3. **Or both:** Broader news and longer price data maximize the continuous period.

The script prints a **TIP** when overlap &lt; 6 months:  
*“For 6+ months ensure price and news both cover the same period (e.g. news from at least 6 months before price end).”*

---

## 5. Expected When You Have 6+ Months

When overlap ≥ 6 months you should see:

- **Months in period:** 6–12 calendar months (e.g. `['2022-06', '2022-07', ..., '2022-11']`).
- **Expected rebalances:** 24+ (roughly 4 Mondays per month).
- **Gemini:** 1 ranking + (weeks × tickers) analyses; use cache for faster reruns.
- **Results:** Full-period Sharpe, return, drawdown for technical_only, news_only, combined, plus “News vs technical” and best approach.

---

## 6. Summary

- **Logic:** 6–12 month continuous period with overlapping price and news is implemented and logged (months, rebalances, Gemini estimate).
- **Current data:** Overlap for the 5-ticker run is 2.3 months → 2 months and 5 rebalances used; Sharpes and “news vs technical” are over that period.
- **News vs technical:** In this run, news_only had the best Sharpe (3.89); news did not underperform technical.
- **Next step:** Widen news and/or price coverage so overlap ≥ 6 months, then rerun to get 24+ rebalances and statistically stronger results for presentation.
