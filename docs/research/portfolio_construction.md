# Portfolio Construction — Research

**Status:** Implemented (Project Freeze)  
**Entry point:** `scripts/portfolio_optimizer.py`  
**Outputs:** `outputs/last_valid_weights.json`, `outputs/last_optimized_weights.json`

---

## 1. Overview

The production pipeline previously used a hardcoded top-3 equal-weight selection from the signal table. This document describes the replacement: a **Volatility-Adjusted Alpha Tilt** optimizer that allocates weight by score per unit of risk (30-day rolling volatility) and applies a configurable cap per position.

---

## 2. Volatility-Adjusted Alpha Tilt Method

### 2.1 Inputs

- **last_signal.json** — Per-ticker fields: `score`, `weight`, `latest_close`, `notional_units`. Scores are ML-blended (0–1).
- **Price CSVs** — Loaded via `load_data_config()` and `load_prices(data_dir, tickers)` for all tickers present in the signal. Each series must have a `close` column and a DatetimeIndex.

### 2.2 Parameters

| Parameter      | Default | Description |
|----------------|---------|-------------|
| `top_quantile` | 0.75    | Quantile cutoff — dynamic; e.g. 0.75 means top 25% of universe scores are eligible. |
| `score_floor`  | 0.50    | Hard minimum score; no ticker with score ≤ floor is eligible (prevents neutral/bearish names in low-signal regimes). |
| `max_weight`   | 0.25    | Maximum weight per ticker after normalization and cap. |
| `vol_window`   | 30      | Rolling window (trading days) for volatility. |

### 2.3 Algorithm

1. **Scores** — Build `scores = {ticker: float(score)}` for all tickers with non-null score in `last_signal.json`.
2. **Volatility** — For each ticker with price data:  
   `returns = close.pct_change().dropna()`  
   `vol = returns.iloc[-vol_window:].std()`  
   Tickers with insufficient data, or `vol == 0` or NaN, are excluded from the eligible set.
3. **Eligibility** — `score_threshold = np.quantile(scores.values(), top_quantile)`; `effective_threshold = max(score_threshold, score_floor)`; eligible tickers: `score > effective_threshold` and vol computed successfully.
4. **Fallback** — If no ticker is eligible: take top 3 by score, assign equal weight 1/3 each, and skip optimization (log warning).
5. **Raw weights** — For each eligible ticker:  
   `raw_w[t] = score[t] / vol[t]`
6. **Normalize** — `w[t] = raw_w[t] / sum(raw_w)` so weights sum to 1.
7. **Iterative cap at max_weight**  
   - While any `w[t] > max_weight`:  
     - Capped set: tickers with `w[t] > max_weight`; set their weight to `max_weight`.  
     - Excess = sum of (previous weight − max_weight) over capped.  
     - If there is an uncapped set: redistribute excess to uncapped proportionally to their current weights.  
     - If all are capped: break (weights remain at max_weight; total may exceed 100% or be normalized per implementation).
8. **Outputs**  
   - **last_valid_weights.json** — `{"as_of": "YYYY-MM-DD", "weights": {"TICKER": weight, ...}}` for consumption by execution.  
   - **last_optimized_weights.json** — Full run: method name, params, weights, and per-ticker metadata (score, vol_30d, raw_weight).

### 2.4 Rationale

- **Score / vol** — Allocates more to higher alpha per unit of risk.  
- **Cap** — Limits concentration and single-name risk.  
- **Fallback** — Ensures a valid weight vector even when no ticker passes the score or vol filters.

---

## 3. Integration

- **daily_workflow.py** — Step 3.5 runs `portfolio_optimizer.py` after `generate_daily_weights.py` and before paper execution (3b). If the script exits non-zero, a warning is logged and `last_valid_weights.json` is left unchanged.
- **run_execution.py** — Uses `last_valid_weights.json` (or equivalent) for rebalance mode; no change to the execution script required for this deliverable.

---

## 4. References

- Signal pipeline: `scripts/generate_daily_weights.py`, `outputs/last_signal.json`
- Data: `src.data.csv_provider.load_data_config`, `load_prices`
- Execution: `scripts/run_execution.py --rebalance`
