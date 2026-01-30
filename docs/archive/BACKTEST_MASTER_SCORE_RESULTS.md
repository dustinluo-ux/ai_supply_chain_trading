# Technical Library (Master Score) Backtest Results

**Strategy:** Expanded indicator universe + category-weighted Master Score (Trend 40%, Momentum 30%, Volume 20%, Volatility 10%). Weekly rebalance, equal-weight top-N. No news; technical only.

**Script:** `scripts/backtest_technical_library.py`  
**Config:** `config/technical_master_score.yaml` (category weights, rolling window 252)

---

## Run 1: Full 2022 (5 tickers, top-3)

| Metric        | Value    |
|---------------|----------|
| Period        | 2022-01-03 to 2022-12-12 |
| Rebalances    | 50       |
| **Sharpe**    | **-0.75** |
| Total return  | -33.64%  |
| Max drawdown  | -48.25%  |

**Interpretation:** 2022 was a bear year for tech; negative return and Sharpe are expected. The strategy underperformed in this period.

---

## Run 2: Oct–Nov 2022 (5 tickers, top-3)

| Metric        | Value    |
|---------------|----------|
| Period        | 2022-10-03 to 2022-11-28 |
| Rebalances    | 9        |
| **Sharpe**    | **0.11** |
| Total return  | +14.94%  |
| Max drawdown  | -12.39%  |

**Interpretation:** Positive return and slightly positive Sharpe over this 2-month window. Higher return than the legacy technical-only run (11.36%) but lower Sharpe (legacy technical-only Oct–Nov: Sharpe 2.68), suggesting the Master Score portfolio had higher volatility.

---

## Comparison with legacy technical-only (from existing backtests)

| Period              | Strategy        | Sharpe | Return   | Max DD   |
|---------------------|-----------------|--------|----------|----------|
| 2 months (Oct–Nov)  | Legacy technical| 2.68   | 11.36%   | -6.65%   |
| 2 months (Oct–Nov)  | **Master Score**| **0.11**| **14.94%**| -12.39% |
| 9 months (Apr–Dec)  | Legacy technical| -0.63  | -16.42%  | -31.14%  |
| 12 months (Jan–Dec) | **Master Score**| **-0.75**| **-33.64%**| -48.25% |

- **Master Score** uses many more indicators (MACD, ADX, ATR, RSI, Stoch, WillR, ROC, CCI, OBV, CMF, volume ratio, BB, etc.) and category weighting; legacy uses momentum + volume + RSI only.
- Over 2 months the new strategy delivered higher return but lower Sharpe (more volatile). Over 2022 full year both strategies lost; Master Score lost more in this test (5-ticker universe).

---

## How to reproduce

```bash
# Full 2022 (5 tickers, top-3)
python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3

# Oct–Nov 2022 only
python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM,AAPL,MSFT --top-n 3 --start 2022-10-01 --end 2022-11-30
```

Logs are written to `outputs/backtest_master_score_YYYYMMDD_HHMMSS.txt`.

---

## Next steps (suggested)

1. Run with larger universe (e.g. 15 tickers, top-10) and same date range as `test_signals.py` for direct comparison.
2. Add a combined mode: rank by (Master Score + news score) and backtest.
3. Tune category weights in `config/technical_master_score.yaml` and re-run to test sensitivity.
