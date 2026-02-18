# BACKTEST_JOURNAL — Execution Assumptions & Results

**Last Updated:** 2026-02-14

This document records execution assumptions, safety audits, path-dependency safeguards, and backtest results for the Technical Library Master Score backtest (`scripts/backtest_technical_library.py`). 

**Indicator mathematics:** See `TECHNICAL_SPEC.md`  
**Architecture and data flow:** See `ARCHITECTURE.md`

---

## 1. Execution Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Signal generation** | Monday market close | Weekly frequency |
| **Order execution** | **Next-Day Open** | Tuesday open for Monday signals |
| **No look-ahead** | Strict | Orders filled at first available price after signal |

**Return calculation:**

| Period | Formula |
|--------|---------|
| **Entry day** (first day of position) | `(Close − Open) / Open` |
| **Subsequent days** | `(Close_t − Close_t-1) / Close_t-1` |

**Rationale:** Open-to-close on entry day captures intraday move; close-to-close thereafter captures overnight gaps and full daily performance.

---

## 2. Transaction Costs

| Setting | Value |
|---------|-------|
| **Friction model** | Fixed per-trade cost |
| **Slippage + Commission** | **0.15%** (15 basis points) |
| **Application** | Deducted from portfolio return on rebalance dates |
| **Code location** | `FRICTION_BPS = 15` in `scripts/backtest_technical_library.py` |

**Coverage:** Includes estimated market impact, bid-ask spread, and broker commission.

**Future enhancement:** Dynamic friction model based on:
- Spread estimation from market data
- Impact calculation from order size vs average volume
- Liquidity-adjusted slippage

---

## 3. Position Sizing

| Parameter | Value/Method |
|-----------|--------------|
| **Sizing method** | **Inverse Volatility Weighting** |
| **Formula** | `weight_i ∝ 1 / (ATR_norm_i + ε)` |
| **Volatility proxy** | ATR_norm (normalized Average True Range) |
| **ATR timing** | **Signal Day − 1** (no same-day volatility leak) |
| **Normalization** | Active positions sum to 100% |

**Implementation detail:**
```python
# When computing weights for signal date T:
row_sizing = indicators_df.iloc[-2]  # Uses T-1 data when len >= 2
ATR_norm_value = row_sizing['ATR_norm']
```

**Rationale:**
- Higher risk → smaller allocation
- Automatic risk balancing across portfolio
- No look-ahead violation

---

## 4. Systemic Risk Management & 3-State Regime

### 4.1 Benchmark

**Ticker:** SPY (S&P 500 ETF)

**Data location:** `data/stock_market_data/sp500/csv/SPY.csv`

**Usage:**
- Regime detection via HMM
- Trend confirmation via 200-day SMA
- Performance benchmark

### 4.2 Three-State Regime Detection

**Method:** Gaussian Hidden Markov Model (3 components)

**Engine:** hmmlearn library

**States (mapped by mean return):**

| State | Characteristics | Category Weights | Position Sizing |
|-------|----------------|------------------|-----------------|
| **BULL** | High mean return, low volatility | BULL_WEIGHTS (aggressive) | Standard (100%) |
| **BEAR** | Negative mean return, high volatility | DEFENSIVE_WEIGHTS (conservative) | Reduced or CASH_OUT |
| **SIDEWAYS** | Mean ≈ 0, moderate volatility | SIDEWAYS_WEIGHTS (balanced) | 50% reduction |

**State mapping logic:**
```python
# After HMM fit on SPY returns:
means = [state.mu for state in hmm_states]
highest_mean_idx = argmax(means)  # → BULL
lowest_mean_idx = argmin(means)   # → BEAR
middle_idx = remaining             # → SIDEWAYS
```

### 4.3 Cash-Out Rule (Dual-Confirmation)

**Trigger condition:** Regime = BEAR **AND** SPY < 200-SMA

**Actions:**

| Mode | Action |
|------|--------|
| `cash` | 100% cash position |
| `half` | 50% position size reduction |

**Code location:** `KILL_SWITCH_MODE` in `scripts/backtest_technical_library.py`

**Rationale:** Dual-confirmation prevents false signals during volatile bull markets where HMM may classify as BEAR due to high volatility.

### 4.4 Sideways Scaling

**Trigger:** Regime = SIDEWAYS

**Action:** Multiply all signals by 0.5

**Implementation:**
```python
if regime_state == "SIDEWAYS":
    signals_df *= 0.5
```

**Rationale:** Reduce exposure during choppy, range-bound markets.

### 4.5 Kill-Switch Modes

| Mode | SPY < 200-SMA | Regime = BEAR | Action |
|------|---------------|---------------|--------|
| Without SPY data | N/A | N/A | Kill-switch OFF |
| With SPY data | No | Yes | Position × 0.5 (sideways scaling if applicable) |
| With SPY data | Yes | Yes | **CASH_OUT** (100% cash) |
| With SPY data | Yes | No/Unknown | Position × 0.5 |

**When regime unknown (None):** Kill-switch branch not applied; only SMA-based reduction may occur.

---

## 5. Critical Safety Audit

### 5.1 Signal Lag Verification

**Rule:** Position × return must use correct alignment.

**Implementation:**
- `positions_df` = weight at **start of day D**
- `returns` = percent change **during day D**
- No `.shift(1)` applied to positions

**Entry timing:** Next-Day Open ensures no look-ahead.

### 5.2 Mid-Week Exit Logic

**Trigger:** Single-day return ≤ `DAILY_EXIT_PCT` (e.g. −5%)

**Action:**
- Set position to 0 from trigger day to end of week
- No reallocation of exited capital to remaining stocks

**Implementation:**
```python
if daily_return <= DAILY_EXIT_PCT:
    position[ticker] = 0  # From this day forward in current week
```

**Entry restriction:** New positions only on Mondays; exits any weekday.

**Consequence:** Portfolio return = `sum(position_i × return_i)` where sum of positions can drop below 1.0 after exits.

### 5.3 Benchmark Alignment

**Requirements:**
- SPY data reindexed to match universe `all_dates`
- Forward fill (`ffill`) for missing dates
- Timezone: tz-naive (matching price data)

**Verification:**
- No timestamp leakage
- Same calendar as portfolio
- No future data in SPY returns

---

## 6. Path Dependency Safeguards

### 6.1 ATR Sizing Lag

**Volatility data source:** ATR_norm from **Signal Day − 1**

**Code implementation:**
```python
# When indicators_df has sufficient history (len >= 2):
row_sizing = indicators_df.iloc[-2]  # T-1 data
ATR_norm_value = row_sizing['ATR_norm']
```

**Verification:** No same-day volatility leak.

### 6.2 Mid-Week Cash Treatment

**Rule:** Exited capital is **NOT** reallocated.

**Example:**
```
Monday: 3 positions @ 33.3% each = 100% invested
Wednesday: Position A exits due to −5% loss
Result: Position A = 0%, B = 33.3%, C = 33.3%
Total invested: 66.6% (33.4% cash)
```

**Portfolio return calculation:**
```python
portfolio_return = sum(position_i × return_i)
# Where sum(position_i) may be < 1.0
```

**Rationale:** Prevents "teleporting" cash; more realistic execution model.

---

## 7. How to Run

### 7.1 Basic Backtest

```bash
# Full 2022 (5 tickers, top-3 selection)
python scripts/backtest_technical_library.py \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3 \
    --start 2022-01-01 \
    --end 2022-12-31
```

**Output:** `outputs/backtest_master_score_YYYYMMDD_HHMMSS.txt`

### 7.2 Dynamic Weighting Modes

```bash
# Regime-based (HMM 3-state)
python scripts/backtest_technical_library.py \
    --weight-mode regime \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3

# Rolling optimization (max Sharpe)
python scripts/backtest_technical_library.py \
    --weight-mode rolling \
    --rolling-method max_sharpe \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3

# Rolling optimization (Hierarchical Risk Parity)
python scripts/backtest_technical_library.py \
    --weight-mode rolling \
    --rolling-method hrp \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3

# Machine learning (Random Forest + CV)
python scripts/backtest_technical_library.py \
    --weight-mode ml \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3
```

### 7.3 News Overlay

```bash
# 80% Technical + 20% News Composite
python scripts/backtest_technical_library.py \
    --news-dir data/news \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3
```

**State logging:** `[STATE]` shows `News Buzz: T/F` when active.

### 7.4 Skip Safety Report

```bash
python scripts/backtest_technical_library.py \
    --no-safety-report \
    [... other args ...]
```

---

## 8. Model Validation & State Logging

### 8.1 State Logging Format

**When enabled:** `--weight-mode regime` or `--news-dir` set

**Format:**
```
[STATE] {Date} | Regime: B/E/S | News Buzz: T/F/- | Action: Trade/Cash
```

**Legend:**
- **Regime:** B=Bull, E=Bear, S=Sideways
- **News Buzz:** T/F when news data active; `-` otherwise
- **Action:** Trade=hold positions (possibly scaled); Cash=100% cash (CASH_OUT)

### 8.2 HMM Transition Matrix

**When logged:** First Monday only (once per run)

**Condition:** `--weight-mode regime` and verbose logging enabled

**Format:**
```
[HMM TRANSITION MATRIX]
[[p_BB, p_BE, p_BS],
 [p_EB, p_EE, p_ES],
 [p_SB, p_SE, p_SS]]

Diagonals: [p_BB, p_EE, p_SS] (target > 0.80 for stable regime)
```

**Interpretation:**
- **High diagonals (>0.80):** Stable regime, low flip-flopping
- **Low diagonals (<0.50):** High volatility warning, frequent transitions

### 8.3 Regime Sanity Check

**Format:**
```
[REGIME] Date: {monday}, HMM State: {state}, Mean Return: {mu}, Volatility: {sigma}
```

**Verification:**
- BEAR should have lower mean and higher volatility than BULL
- SIDEWAYS should have moderate mean (~0) and moderate volatility

### 8.4 Weight Bounds (Rolling Mode)

**PyPortfolioOpt:** `weight_bounds=(0.10, 0.50)`

**Constraint:** No category weight < 10% or > 50%

**HRP method:** Clip then renormalize to maintain bounds.

### 8.5 ML Fallback Logging

**Format:**
```
[ML] CV R²: {value}
```

**Fallback condition:** If R² < 0:
```
[ML] Fallback to fixed weights (R² < 0)
```

### 8.6 News Overlay Formula

**Configuration:** `news_weight: 0.20` in `config/technical_master_score.yaml`

**Formula:**
```
Final_Score = 0.8 × Technical_Score + 0.2 × News_Composite
```

**News composite components:**
- Strategy A: Buzz (volume z-score)
- Strategy B: Surprise (sentiment delta)
- Strategy C: Sector Relative (cross-sectional ranking)
- Strategy D: Event-Driven (catalyst detection)

---

## 9. Quantitative Health Checks

### 9.1 Pre-Backtest Verification

Run these checks before executing full backtest:

| Check | What to Verify | Where to Look |
|-------|----------------|---------------|
| **1. Persistence** | HMM transition matrix diagonals > 0.80 | `[HMM TRANSITION MATRIX]` in backtest log |
| **2. Surprise Lag** | Strategy B baseline excludes signal date | `src/signals/news_engine.py` → `strategy_surprise` → `cutoff_baseline <= d < as_of` |
| **3. Dual-Confirmation** | CASH_OUT requires BEAR + SPY < 200-SMA | `scripts/backtest_technical_library.py` → `if regime_state == "BEAR" and spy_below_sma200` |

**Persistence check detail:**
```python
# High diagonals (>0.80) indicate:
p_BB > 0.80  # Bull → Bull persistence
p_EE > 0.80  # Bear → Bear persistence
p_SS > 0.80  # Sideways → Sideways persistence

# Low diagonals (<0.50) indicate:
# Frequent regime switching → transaction cost risk
```

**Surprise lag rule:**
```python
# Strategy B (News Surprise) baseline calculation:
baseline_vals = sentiment[cutoff_baseline <= date < as_of]
# Excludes as_of date from baseline to prevent "washing out" surprise
```

**Dual-confirmation verification:**
```python
# CASH_OUT triggered only when BOTH conditions true:
if regime_state == "BEAR" and spy_below_sma200:
    action = "CASH_OUT"
```

---

## 10. Results Summary

### 10.1 Full 2022 Backtest

| Metric | Master Score (5 tickers, top-3) | SPY 2022 (reference) |
|--------|----------------------------------|----------------------|
| **Sharpe Ratio** | −0.75 | ~−0.72 |
| **Total Return** | −33.64% | ~−18.1% |
| **Max Drawdown** | −48.25% | ~−25.3% |

**Period:** 2022-01-01 to 2022-12-31  
**Universe:** NVDA, AMD, TSM, AAPL, MSFT  
**Selection:** Top 3 by Master Score

**Notes:**
- 2022 was a bear market year
- Master Score strategy underperformed SPY
- Higher drawdown indicates insufficient defensive positioning

### 10.2 October-November 2022

| Metric | Master Score | Notes |
|--------|--------------|-------|
| **Sharpe Ratio** | 0.11 | Positive risk-adjusted return |
| **Total Return** | +14.94% | Strong recovery period |
| **Max Drawdown** | −12.39% | Moderate pullback |

**Period:** 2022-10-01 to 2022-11-30  
**Context:** Market rebound from October lows

### 10.3 Legacy vs Master Score Comparison

**2022 full year comparison:**
- **Master Score:** Trend 40% + Momentum 30% + Volume 20% + Volatility 10%
- **Legacy:** Momentum + Volume + RSI only

**Observations:**
- Both strategies lost money in 2022 bear market
- Master Score had higher total return but lower Sharpe in Oct-Nov
- Category-weighted approach provides more diversified signal

---

## 11. Model Comparison (Q2 2022)

### 11.1 Hypothesis

**HRP (Hierarchical Risk Parity) should have lower max drawdown than max_sharpe (EfficientFrontier) in Q2 2022 because HRP does not overfit to noisy rallies.**

### 11.2 Commands

```bash
# Q2 2022 – max_sharpe (EfficientFrontier)
python scripts/backtest_technical_library.py \
    --weight-mode rolling \
    --rolling-method max_sharpe \
    --start 2022-04-01 \
    --end 2022-06-30 \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3 \
    --no-safety-report

# Q2 2022 – hrp (Hierarchical Risk Parity)
python scripts/backtest_technical_library.py \
    --weight-mode rolling \
    --rolling-method hrp \
    --start 2022-04-01 \
    --end 2022-06-30 \
    --tickers NVDA,AMD,TSM,AAPL,MSFT \
    --top-n 3 \
    --no-safety-report
```

### 11.3 Results (Template)

| Method | Sharpe | Total Return | Max Drawdown |
|--------|--------|--------------|--------------|
| **max_sharpe** | *run locally* | *run locally* | *run locally* |
| **hrp** | *run locally* | *run locally* | *run locally* |

**Analysis:** Fill table after running locally and compare max drawdowns.

---

## 12. Autonomous Run: 2022 Regime + News Overlay

### 12.1 Objective

Execute full 2022 backtest with:
- 3-State Regime detection (HMM)
- News Alpha overlay (20%)
- Verify CASH_OUT during Q2/Q4 2022 drawdowns

### 12.2 Command

```bash
# Bash/PowerShell
python scripts/backtest_technical_library.py \
    --start 2022-01-01 \
    --end 2022-12-31 \
    --weight-mode regime \
    --news-dir data/news \
    --tickers AAPL,MSFT,NVDA,AMD,TSLA \
    --top-n 3
```

**Notes:**
- **CLI aliases:** `--start`/`--end` = `--start-date`/`--end-date`
- **News weight:** Set in `config/technical_master_score.yaml` (default 0.20)
- **Kill-switch mode:** `KILL_SWITCH_MODE` in script (default `cash`)

### 12.3 Data Requirements

**Ticker availability:**
- **In repo:** AAPL, MSFT, NVDA, AMD, TSLA (from sp500/nasdaq/forbes2000/csv)
- **May be missing:** GOOGL, META (add CSV or exclude from list)

**SPY benchmark:**
- **Generate:** Run `scripts/download_spy_yfinance.py` (network required)
- **Or:** Run `scripts/generate_spy_placeholder.py` (no network, synthetic data)
- **Location:** `data/stock_market_data/sp500/csv/SPY.csv`
- **Without SPY:** Kill-Switch and HMM regime detection OFF

**News data:**
- **FinBERT model:** ProsusAI/finbert loaded on first use
- **Network:** HuggingFace download (may hang if proxy blocks)
- **Offline:** Place in `./models/finbert` directory
- **Skip news:** Omit `--news-dir` for regime-only mode

### 12.4 Expected Outcomes

| Metric | Strategy (2022) | SPY 2022 (reference) |
|--------|-----------------|----------------------|
| **Sharpe** | *run locally* | ~−0.72 |
| **Total Return** | *run locally* | ~−18.1% |
| **Max Drawdown** | *run locally* | ~−25.3% |

**Cash-Out rule verification:**
- Expect `Action: Cash` or `CASH_OUT` in logs during:
  - Q2 2022 (April-June) when HMM = BEAR and SPY < 200-SMA
  - Q4 2022 (October-December) during drawdowns

---

## 13. Local Run Audit: Environment & Dependencies

### 13.1 SPY Index Data

**Check:** `data/stock_market_data/sp500/csv/SPY.csv` exists

**If missing:**

**Option 1 (network):**
```bash
python scripts/download_spy_yfinance.py
# Downloads SPY 2015-01-01 to 2023-01-01 via yfinance
```

**Option 2 (no network):**
```bash
python scripts/generate_spy_placeholder.py
# Creates synthetic SPY 2015-2022 for Kill-Switch and HMM
# Replace with real data when possible
```

### 13.2 FinBERT (News Overlay)

**Requirement:** FinBERT model for sentiment analysis

**Network mode:**
- Backtest loads FinBERT on first use
- HuggingFace download via transformers library
- May hang if proxy blocks download

**Offline mode:**
- Clone HuggingFace `ProsusAI/finbert` repository
- Place in `./models/finbert` directory
- `news_engine.py` checks this path first
- Uses `local_files_only=True`

**Skip news:**
- Run without `--news-dir` for regime-only mode
- No FinBERT required

### 13.3 Local Run Confirmation

| Check | Status | Evidence |
|-------|--------|----------|
| **SPY data for Kill-Switch** | Yes (when CSV exists) | Log: `Kill-Switch: ON (SPY < 200 SMA -> cash)` |
| **SPY data for HMM regime** | Yes (when CSV exists) | Log: `[STATE] ... \| Regime: B/E/S \| ...` |
| **HMM transition matrix** | Yes (first Monday) | `[HMM TRANSITION MATRIX]` with diagonals |
| **Dual-confirmation** | Yes (Q2/Q4 2022) | `Action: Cash` when Regime E + SPY < 200-SMA |

### 13.4 Results Template (Fill After Local Run)

After executing full 2022 run, update:

**Performance metrics:**
- Sharpe: *value*
- Total return: *value*
- Max drawdown: *value*

**HMM diagnostics:**
- Diagonals (first Monday): *e.g. [0.85, 0.82, 0.79]* → stable / or *< 0.5* → High Volatility Warning

**Cash-Out events:**
- Q2 2022: Yes/No *(list dates if Yes)*
- Q4 2022: Yes/No *(list dates if Yes)*

---

## 14. Safety Report (Terminal Output)

**Default:** Safety Report prints after each backtest

**Contents:**
- Signal lag verification
- Mid-week exit validation
- Benchmark alignment checks
- Data quality metrics

**Skip report:**
```bash
python scripts/backtest_technical_library.py --no-safety-report [... args ...]
```

**Rationale:**
- Validates no look-ahead violations
- Documents execution assumptions
- Builds confidence in backtest integrity

---

## 15. Stress Testing

### 15.1 2022 Stress Test Guidance

**Full year:** 2022-01-01 to 2022-12-31

**If timeout in CI:** Run four quarters locally and aggregate:

```bash
# Q1
python scripts/backtest_technical_library.py --start 2022-01-01 --end 2022-03-31 ...

# Q2
python scripts/backtest_technical_library.py --start 2022-04-01 --end 2022-06-30 ...

# Q3
python scripts/backtest_technical_library.py --start 2022-07-01 --end 2022-09-30 ...

# Q4
python scripts/backtest_technical_library.py --start 2022-10-01 --end 2022-12-31 ...
```

**Aggregate returns:**
```python
total_return = (1 + R_Q1) × (1 + R_Q2) × (1 + R_Q3) × (1 + R_Q4) − 1
```

---

This journal is the authoritative record of backtest execution details and results. All assumptions documented here must be verified in code before production use.
