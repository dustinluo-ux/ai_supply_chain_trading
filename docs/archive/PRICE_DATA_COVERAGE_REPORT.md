# Price Data Coverage Report

**Date:** 2026-01-29  
**Purpose:** Determine maximum backtest period from price CSV coverage for key universe tickers and recommend FNSPID processing range.

---

## TASK 1: Price CSV Date Ranges (Top 9 Tickers)

Key tickers: **NVDA, AMD, TSM, AAPL, MSFT, INTC, QCOM, MU, AMAT** (top AI supply chain from recent backtest).

| Ticker | Earliest | Latest | Days | Coverage | File |
|--------|----------|--------|------|----------|------|
| NVDA   | 1999-01-22 | 2022-12-12 |  6013 | OK       | data/stock_market_data/nasdaq/csv/NVDA.csv |
| AMD    | 1980-03-17 | 2022-12-12 | 10778 | OK       | data/stock_market_data/nasdaq/csv/AMD.csv |
| TSM    | 1997-10-09 | 2022-12-12 |  6336 | OK       | data/stock_market_data/nyse/csv/TSM.csv |
| AAPL   | 1980-12-12 | 2022-12-12 | 10590 | OK       | data/stock_market_data/nasdaq/csv/AAPL.csv |
| MSFT   | 1986-03-13 | 2022-12-12 |  9264 | OK       | data/stock_market_data/nasdaq/csv/MSFT.csv |
| INTC   | 1980-03-17 | 2022-12-12 | 10778 | OK       | data/stock_market_data/nasdaq/csv/INTC.csv |
| QCOM   | 1991-12-13 | 2022-12-12 |  7808 | OK       | data/stock_market_data/nasdaq/csv/QCOM.csv |
| MU     | 1984-06-01 | 2022-12-12 |  9713 | OK       | data/stock_market_data/nasdaq/csv/MU.csv |
| AMAT   | 1980-03-17 | 2022-12-12 | 10778 | OK       | data/stock_market_data/nasdaq/csv/AMAT.csv |

**Notes:**
- All files use **Date** as first column (DD-MM-YYYY); no material gaps (coverage OK).
- **Latest date is the same for all: 2022-12-12.** Price data does **not** extend into 2023.
- Earliest date (intersection) is **1999-01-22** (NVDA); any backtest over all 9 tickers is limited to 1999–2022.

---

## Overall Min/Max Across All Tickers

- **Earliest (intersection):** 1999-01-22 (NVDA start).  
- **Latest (intersection):** 2022-12-12 (all tickers end on this date).  
- **Conclusion:** Price data for this universe **ends at 2022-12-12**. There is **no 2023 price data** in these CSVs.

---

## TASK 2: Overlap with News

### Scenario A: Current news (Oct–Dec 2022)

- **News range:** Oct 2022 – Dec 2022 (current `data/news/` for universe tickers).  
- **Price range:** Through 2022-12-12.  
- **Overlap:** Oct 2022 – Dec 2022.  
- **Overlap period:** ~2.3 months.  
- **Rebalances:** ~10 weeks (Mondays in range, minus 30-day tech buffer).  

*(Matches what we observed in the 6-month expansion run.)*

### Scenario B: Extended news (Apr 2022 – Dec 2023)

- **News range (after re-processing FNSPID):** Apr 2022 – Dec 2023.  
- **Price range:** Through 2022-12-12 only (no 2023 prices).  
- **Overlap:** Apr 2022 – **Dec 2022** (price end caps the overlap).  
- **Overlap period:** **9 months** (Apr–Dec 2022).  
- **Rebalances:** ~36 weekly rebalances (after 30-day tech buffer).  

We **cannot** use news beyond Dec 2022 for backtest until we have 2023 price data; overlap is limited by the price end date.

---

## TASK 3: Recommended Processing Strategy

**Finding:** Prices extend through **Dec 2022 only**, not Dec 2023.

**Recommendation:**

1. **Process FNSPID: Apr 2022 – Dec 2022 (9 months)**  
   - Aligns with available price data.  
   - Gives **9 months** of overlapping price + news and **~36 rebalances** (6+ months, statistically useful).

2. **Do not** process FNSPID through Dec 2023 for backtest **until** 2023 price data is available.  
   - You can still ingest Apr 2022 – Dec 2023 for other uses (e.g. future train/test when 2023 prices exist).

3. **If you add 2023 price data later:**  
   - Then process FNSPID Apr 2022 – Dec 2023 (21 months).  
   - Backtest period could be Apr 2022 – Dec 2023 (~84 rebalances).  
   - Train 2022 / test 2023 would become possible.

**Recommended FNSPID processing command (for current price coverage):**

```bash
python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input data/raw/fnspid_nasdaq_news.csv
```

(Add `--no-filter-universe` if you want all tickers.)

---

## TASK 4: Summary

| Item | Value |
|------|--------|
| **Price data end date (all 9 tickers)** | 2022-12-12 |
| **Recommended FNSPID date range** | 2022-04-01 to 2022-12-31 (9 months) |
| **Expected backtest period after re-processing** | Apr 2022 – Dec 2022 (~9 months, ~36 rebalances) |
| **6+ months overlap achievable?** | **Yes** – 9 months overlap once FNSPID is re-processed for Apr–Dec 2022. |
| **Additional price download needed for current backtest?** | **No** – existing CSVs through Dec 2022 are sufficient for a 9-month backtest. |
| **Additional price download for 2023 backtest?** | **Yes** – to backtest or train/test into 2023, 2023 price data must be added. |

---

## Expected Final Backtest Period (After Re-Processing FNSPID)

- **Months:** 9 (Apr 2022 – Dec 2022).  
- **Rebalances:** ~36 weekly rebalances (Mondays in range, minus 30-day buffer).  
- **Command to extend news:**  
  `python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input data/raw/fnspid_nasdaq_news.csv`

This gives a single, consistent recommendation: **process Apr–Dec 2022 only** for the current price set; extend to 2023 only after adding 2023 price data.
