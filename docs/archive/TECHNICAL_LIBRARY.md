# Technical Indicator Library

**Module:** `src.signals.technical_library`  
**Config:** `config/technical_master_score.yaml` (category weights, rolling window, indicator→category mapping)  
**Purpose:** Professional-grade technical indicators using **pandas_ta** for all calculations. Normalization uses **static formulas** for bounded indicators and **rolling min-max** for unbounded ones to avoid look-ahead bias. Master Score is **category-weighted** (Trend 40%, Momentum 30%, Volume 20%, Volatility 10%).

---

## 1. Normalization Logic

### Why we switched away from global MinMaxScaler

Using a **global** MinMaxScaler (fit on the entire history) would scale each value using the min/max over **all** time. That introduces **look-ahead bias**: at any past date, the “normalized” value would depend on future data (the full-sample min/max). For backtests and live use, normalization must use only information available at that time.

### Static scaling for bounded indicators (no future data)

For **RSI**, **Stochastic**, and **Williams %R** we do **not** use MinMaxScaler. We use fixed formulas so that the same raw value always maps to the same normalized value, regardless of the rest of the series:

- **RSI / Stochastic:** `value / 100` (clip to 0–100, then divide).  
  Example: RSI 70 → 0.7 everywhere.
- **Williams %R:** `(value + 100) / 100` (value in [-100, 0]).  
  Example: -50 → 0.5.

So an RSI of 70 is always 0.7, independent of historical extremes in the series.

### Rolling scaling for unbounded indicators (no look-ahead)

For **unbounded** indicators (ATR, Volume Ratio, MACD, ROC, CCI, momentum 5d/20d, OBV, CMF, ADX, BB position), we use a **rolling min-max** over the **past 252 trading days** (≈ 1 year):

- At each date `t`, min and max are taken over `t-251` to `t` only.
- Normalized value = `(x - rolling_min) / (rolling_max - rolling_min + 1e-8)`, then clipped to 0–1 and NaN filled with 0.5.

This way each value is scaled only against its **past** year of data, so there is **no look-ahead bias**. The window length (252) is configurable in `config/technical_master_score.yaml` as `rolling_window`.

---

## 2. Category-Weighted Master Score

We moved from a flat average of indicators to a **category-weighted** score so that signal drivers are explicit and weights are easy to tune.

### How it works

1. **Categories and weights** (stored in `config/technical_master_score.yaml`):
   - **Trend:** 40% — e.g. ADX, MACD
   - **Momentum:** 30% — e.g. RSI, Williams %R, Stochastic, ROC, CCI, momentum 5d/20d
   - **Volume:** 20% — e.g. volume ratio, CMF, OBV
   - **Volatility:** 10% — e.g. ATR, BB position

2. **Sub-score per category:**  
   For each category, the sub-score is the **mean** of the normalized values (`*_norm`) of the indicators assigned to that category in the config. Missing indicators are treated as 0.5 (neutral).

3. **Master Score:**  
   `Master Score = 0.40 × Trend_sub + 0.30 × Momentum_sub + 0.20 × Volume_sub + 0.10 × Volatility_sub`

4. **Returned dictionary** from `compute_signal_strength(row)` includes:
   - **`category_sub_scores`:** `{ "trend": float, "momentum": float, "volume": float, "volatility": float }`  
     So you can see which category is driving the signal.
   - **`breakdown`:** Per-indicator normalized values for inspection.

All fixed weights and the list of indicators per category live in **`config/technical_master_score.yaml`** (no weights in code).

---

## 3. Config File: `config/technical_master_score.yaml`

Single source of truth for:

- **`category_weights`:** Trend 40%, Momentum 30%, Volume 20%, Volatility 10%
- **`rolling_window`:** 252 (trading days) for rolling min-max
- **`categories`:** Which `*_norm` columns belong to Trend, Momentum, Volume, Volatility

To change weights or assign indicators to categories, edit this file; the code reads it at runtime.

---

## 4. Entry Point and Indicators

- **`calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame`**  
  Ingest standard OHLCV (columns: `open`, `high`, `low`, `close`, `volume`; index = datetime). Returns OHLCV plus raw indicator columns and `*_norm` columns (0–1). NaN from look-backs are filled with 0.5 in normalized columns.

Indicators (all via pandas_ta): Trend (MACD, ADX, PSAR, Aroon), Volatility (Bollinger, ATR, Keltner), Momentum (Stochastic, CCI, Williams %R, ROC, RSI(14), momentum 5d/20d), Volume (OBV, CMF, VWAP, volume ratio), Moving averages (EMA 8/12/26/50, SMA 50/200, SMA golden cross).

---

## 5. Integration

- **test_signals.py:** After loading price data, prints a **Signal Strength Report** (NVDA or first ticker): Master Score, as-of date, **Category sub-scores** (Trend, Momentum, Volume, Volatility), and top normalized indicators.
- **Existing flow:** `TechnicalIndicators` and `TechnicalAnalyzer` are unchanged; this library is additive.

---

## 6. Dependencies

- `pandas_ta`
- `PyYAML` (for `config/technical_master_score.yaml`)

(No sklearn for normalization: bounded = static formulas, unbounded = rolling min-max.)

---

## 7. Usage Example

```python
from src.signals.technical_library import (
    calculate_all_indicators,
    compute_signal_strength,
    OHLCV_COLS,
)

# df: DataFrame with open, high, low, close, volume
out = calculate_all_indicators(df)
last = out.iloc[-1]
score, result = compute_signal_strength(last)
# result["category_sub_scores"] = { "trend": ..., "momentum": ..., "volume": ..., "volatility": ... }
# result["breakdown"] = { "rsi_norm": ..., ... }
print("Master Score:", score)
print("Category sub-scores:", result["category_sub_scores"])
```
