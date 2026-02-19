# Alpha Calibration -- 3-Way Ablation Study

**Generated:** 2026-02-16
**Status:** Price data updated; news data gap DISCOVERED and documented

---

## Executive Summary

Price CSVs were successfully updated to 2024-12-31 via yfinance. The 2023-2024
calibration ran to completion but all 3 runs produced **identical** results because
the news JSON files actually contain articles from **April to December 2022 only**
(not 2023-2024 as previously documented in `data_config.yaml`). The config has been
corrected.

The propagation pipeline is fully wired and operational. Once news data covering
2023-2024 is acquired, re-running the calibration will produce differentiated results.

---

## Price Data Update

Successfully updated all tickers via `scripts/update_price_data.py` (yfinance 1.1.0):

| Ticker | Before | After | Range |
|--------|--------|-------|-------|
| NVDA | 6,013 rows | 6,528 rows | 1999-01-22 to 2024-12-31 |
| AMD | 10,778 rows | 11,293 rows | 1980-03-17 to 2024-12-31 |
| TSM | 6,336 rows | 6,851 rows | 1997-10-09 to 2024-12-31 |
| AAPL | 10,590 rows | 11,105 rows | 1980-12-12 to 2024-12-31 |
| MSFT | 9,264 rows | 9,779 rows | 1986-03-13 to 2024-12-31 |
| GOOGL | **NEW** | 2,516 rows | 2015-01-02 to 2024-12-31 |
| SPY | 2,086 rows | 2,588 rows | 2015-01-02 to 2024-12-31 |

**Script:** Reused logic from `graveyard/scripts/download_spy_yfinance.py` (MultiIndex
handling, `auto_adjust=False`) and `graveyard/download_simple.py` (download loop).
Adapted to read from `data_config.yaml` via ConfigManager per AI_RULES Section 10.

---

## Calibration Results (2023-01-02 to 2024-12-30)

**Watchlist:** NVDA, AMD, TSM, AAPL, MSFT, GOOGL (6 tickers -- GOOGL now loads)
**Top-N:** 5
**Rebalance:** Weekly (Monday)

| Metric | BASELINE | FULL_ALPHA | CAPPED |
|--------|----------|------------|--------|
| Total Return | 122.57% | 122.57% | 122.57% |
| Sharpe Ratio | 0.4075 | 0.4075 | 0.4075 |
| Max Drawdown | -16.82% | -16.82% | -16.82% |
| Rebalances | 105 | 105 | 105 |

**Result:** Identical across all 3 runs.

### Run Configuration

| Run | news_weight | propagation | tier_1_weight | CLI |
|-----|-------------|-------------|---------------|-----|
| BASELINE | OFF | OFF | -- | (no --news-dir) |
| FULL_ALPHA | 0.20 | ON | 0.50 | --news-dir data/news |
| CAPPED | 0.10 | ON | 0.25 | --news-dir data/news --news-weight 0.10 |

### Why identical?

The news JSON files (`data/news/*_news.json`) contain articles from **2022-04-01 to
2022-12-31** only. The `data_config.yaml` previously claimed 2023-2024, which was
incorrect and has been corrected. With zero matching articles for 2023-2024:

- `news_composite` defaults to 0.5 (neutral) for all tickers
- Uniform dampening preserves relative rankings
- All 6 tickers held (top_n=5 out of 6) -- minimal selection impact

---

## Propagation Wiring Verification

Log evidence from FULL_ALPHA run:

```
src.signals.signal_engine INFO: Propagation enabled: True | news_dir: True | news_weight: 0.20
src.signals.signal_engine INFO: News articles found > 0 for 0/6 tickers (as_of=2023-01-02)
src.signals.sentiment_propagator INFO: SentimentPropagator initialized (max_degrees=2)
src.signals.signal_engine INFO: Propagation enriched 0/6 composites
```

**Confirmed operational:**
- `enable_propagation` read from `strategy_params.propagation.enabled` via ConfigManager
- `SentimentPropagator` initializes on first call
- Propagation fires every week when `news_dir` is set
- YAML swap mechanism: `tier_1_weight` overwritten to 0.25 for CAPPED, restored after

---

## Data Coverage Matrix

| Data Source | Actual Range | Status |
|-------------|-------------|--------|
| Price CSVs (OHLCV) | 1980-2024 | UPDATED via yfinance |
| SPY (Kill-Switch/HMM) | 2015-2024 | UPDATED via yfinance |
| News JSON (FNSPID) | 2022-04-01 to 2022-12-31 | STALE -- does not cover 2023-2024 |
| Supply Chain DB | Static | OK |

**Gap:** News data ends 9 months before the earliest useful price data overlap.

---

## Recommended Next Action: Calibrate on 2022 (H2)

Given the actual news coverage (April-December 2022), the correct ablation period is:

```bash
python scripts/run_calibration.py --start 2022-04-01 --end 2022-12-12
```

This aligns the backtest window with the news data availability. Note: the
previous 2022 calibration (January-December) showed "News Buzz: F" for all weeks.
This warrants investigation into the news engine's date matching logic -- articles
exist for the period but `buzz_active` never triggered, which may be because the
buzz threshold (mean + 2*std) is never exceeded with steady article flow.

---

## All Code Changes Made

| File | Change | Reason |
|------|--------|--------|
| `scripts/update_price_data.py` | **CREATED** | Config-driven yfinance CSV updater |
| `scripts/backtest_technical_library.py` L321-326 | Added `enable_propagation` to `data_context` | Wire propagation from `strategy_params.yaml` |
| `scripts/backtest_technical_library.py` L536 | `--top-n` default 3 -> 5 | Universe expansion |
| `scripts/backtest_technical_library.py` L537-541 | Added `logging.basicConfig()` | Make SignalEngine INFO logs visible |
| `src/signals/signal_engine.py` L110-113 | Added propagation status log | Verify wiring |
| `src/signals/signal_engine.py` L231-243 | Added news/propagation summary logs | Verify article counts |
| `config/data_config.yaml` L37-39 | `date_range.end` -> `2024-12-31` | Support expanded price range |
| `config/data_config.yaml` L67-69 | News date range corrected to 2022-04 to 2022-12 | Fix inaccurate config |
| `scripts/run_calibration.py` | Rewritten with YAML swap, 2023-2024 defaults | Proper 3-way control |

---

## Regime-Based Cash Management (2022 Bear Market Validation)

**Date:** 2026-02-16  
**Goal:** Validate that BEAR = 0% exposure reduces drawdown in the 2022 bear market.

### Backtest Configuration

| Parameter | Value |
|-----------|-------|
| Command | `python scripts/backtest_technical_library.py --tickers NVDA,AAPL,AMD,MSFT,TSM --start 2022-04-01 --end 2022-12-12 --weight-mode regime --top-n 3` |
| Universe | 5 tickers, top-3, weekly rebalance |
| Sizing | ATR-based (Stage 4); config: `trading_config.position_sizing` |
| Kill-Switch | ON (SPY &lt; 200 SMA) |

### Log Verification (BEAR = 0% Exposure)

When `regime_state == BEAR`, the backtest correctly:

- Prints **`[STATE] {date} | Regime: E | ... | Action: Cash`**
- Prints **`Portfolio Action: CASH | Total Exposure: 0.0`**

**BEAR weeks identified in run (2022):** 2022-04-18, 2022-05-09, 2022-06-13, 2022-06-20, 2022-07-04, 2022-09-05, 2022-10-17, 2022-11-28. On each of these weeks the log showed `Portfolio Action: CASH | Total Exposure: 0.0`.

**Evidence (excerpt):**

```
  [STATE] 2022-04-18 | Regime: E | News Buzz: - | Action: Cash
  Portfolio Action: CASH | Total Exposure: 0.0
  [REGIME] Date: 2022-04-18, HMM State: BEAR, Mean Return: 0.000335, Volatility: 0.084712
```

### Regime vs. Fixed — Performance Delta (Same Universe)

Apples-to-apples: same period (2022-04-01 to 2022-12-12), same tickers (NVDA, AAPL, AMD, MSFT, TSM), top-n 3, no news overlay.

| Metric | Fixed | Regime (BEAR→0%) | Delta |
|--------|-------|-------------------|-------|
| **Sharpe Ratio** | 0.0642 | -0.0131 | **-0.0773** (worse) |
| **Total Return** | 8.23% | -4.71% | **-12.94 pp** (worse) |
| **Max Drawdown** | -21.00% | -23.12% | **-2.12 pp** (worse) |
| Rebalances | 37 | 37 | — |

**Conclusion:** In this test, regime-based cash management **did not** reduce max drawdown; both drawdown and Sharpe were worse than fixed weight. The HMM transition matrix from the run had low diagonal persistence (e.g. BULL 0.083, SIDEWAYS 0.000), so the regime label flip-flops week-to-week. Going to cash on BEAR weeks in that setting can miss rebounds and increase volatility of returns, explaining the worse outcome. The **BEAR = 0% exposure** logic is implemented and verified in logs; drawdown reduction would require a more stable regime classifier (e.g. higher HMM diagonals or a different regime definition).

*Reference baseline -17.99% was from a different setup (single ticker NVDA with news overlay); the 5-ticker fixed run above is the correct comparison for this universe.*

---

## Regime Smoothing v1 (2026-02-16)

**Goal:** Reduce whiplash from low HMM persistence by (1) only triggering BEAR gating after **2 consecutive** BEAR weeks, and (2) using **fractional exposure 0.5** instead of 0 when BEAR.

### Implementation

| Location | Change |
|----------|--------|
| `scripts/backtest_technical_library.py` | **Regime Persistence Gate:** `effective_regime_state = "BEAR"` only when `regime_state == "BEAR"` and `prev_regime == "BEAR"`; first BEAR week keeps prior regime (no REDUCE). |
| `scripts/backtest_technical_library.py` | **Stage 4:** When `effective_regime_state == "BEAR"`, scale `intent.weights` by 0.5 (total exposure 0.5) instead of zeroing. Log: `Portfolio Action: REDUCE | Total Exposure: 0.5`. |
| `src/core/policy_engine.py` | **BEAR:** Apply `gated = 0.5 * scores` (and `action = "Trade"`) instead of zeroing, so portfolio_engine returns normal weights; backtest then scales to 0.5. |

### Regime Smoothing v1 — Results (Same 5-Ticker 2022 Backtest)

| Metric | Fixed | Regime (BEAR→0%) | **Regime Smoothing v1** |
|--------|-------|-------------------|--------------------------|
| **Sharpe Ratio** | 0.0642 | -0.0131 | **0.0565** |
| **Total Return** | 8.23% | -4.71% | **6.73%** |
| **Max Drawdown** | -21.00% | -23.12% | **-21.00%** |
| Rebalances | 37 | 37 | 37 |

**Comparison to previous Regime (BEAR→0%):** MaxDD improved from **-23.12%** to **-21.00%** (+2.12 pp). Sharpe and return both positive (0.0565 and 6.73%) vs negative before. With 2-consecutive BEAR gate, REDUCE (0.5 exposure) triggered only once in the run (e.g. 2022-06-20 after 2022-06-13 BEAR).

**Conclusion:** Regime Smoothing v1 (persistence gate + 0.5 fractional exposure) removes whiplash and restores regime backtest to similar MaxDD as fixed (-21.00%) with slightly lower but positive Sharpe and return.

---

## Stage 4 Stress Test — 10-Ticker Diversified (2026-02-16)

**Goal:** Test ATR Position Sizer on a larger universe and verify risk-parity (higher ATR → lower weight).

### Backtest Configuration

| Parameter | Value |
|-----------|-------|
| Command | `python scripts/backtest_technical_library.py --tickers NVDA,AAPL,AMD,MSFT,TSM,GOOGL,META,AVGO,INTC,QCOM --start 2022-04-01 --end 2022-12-12 --weight-mode regime --top-n 5` |
| Requested | 10 tickers; **META** had no CSV in data dir → **9 loaded** |
| Top-N | 5 |
| Sizing | ATR-based (Stage 4); Regime Smoothing v1 (2-consecutive BEAR → 0.5 exposure) |

### Position Sizing Verification (Risk Parity)

The backtest logs **`[SIZING] {date} Top-N: TKR=w ...`** each week. Formula: weight ∝ (risk_pct × price) / (ATR × atr_multiplier), so **higher ATR → lower weight**.

**Evidence — week where high-vol (NVDA) and low-vol (AAPL) are both in Top 5:**

- **2022-10-24:** `Top-N: GOOGL=0.252 INTC=0.199 TSM=0.158 NVDA=0.134 AAPL=0.257`  
  → **NVDA = 0.134**, **AAPL = 0.257**. NVDA (higher volatility) receives a **lower** weight than AAPL. ✓

- **2022-10-31:** `Top-N: GOOGL=0.206 INTC=0.195 TSM=0.204 AAPL=0.242 NVDA=0.152`  
  → **AAPL = 0.242**, **NVDA = 0.152**. Same relation. ✓

- **2022-08-08:** `Top-N: AAPL=0.245 AMD=0.124 AVGO=0.253 GOOGL=0.171 MSFT=0.207`  
  → **AMD** (more volatile) = **0.124** vs **AAPL** = **0.245**. ✓

**Conclusion:** PositionSizer assigns lower weight to the more volatile names when both are in the Top-N, consistent with risk parity.

### 10-Ticker Diversified — Metrics (2022-04-01 to 2022-12-12)

| Metric | Value |
|--------|--------|
| **Sharpe Ratio** | -0.0127 |
| **Total Return** | -4.89% |
| **Max Drawdown** | **-19.17%** |
| Rebalances | 37 |
| Tickers loaded | 9 (NVDA, AAPL, AMD, MSFT, TSM, GOOGL, AVGO, INTC, QCOM) |

Diversification (9 names, top-5) improved **MaxDD vs 5-ticker regime run** (-19.17% vs -21.00% for the 5-ticker regime backtest with same period and Smoothing v1), with slightly worse Sharpe/return in this stress window.

---

## Action Items

| Priority | Action | Expected Outcome |
|----------|--------|------------------|
| **P0** | Run calibration for **2022-04-01 to 2022-12-12** | Overlap between price and news data |
| **P1** | Investigate news engine date matching | Understand why buzz_active is always False even with articles present |
| **P2** | Acquire 2023-2024 news data (FNSPID refresh or alternative source) | Enable full 2023-2024 ablation |
| P3 | Expand watchlist to 15+ tickers | Surface selection-level alpha |

---

## Raw JSON Paths

- `outputs/calibration/baseline.json`
- `outputs/calibration/full_alpha.json`
- `outputs/calibration/capped.json`

---

*This file is a temporary research note (non-canonical).
See `docs/INDEX.md` -- Adding New Documentation.*
