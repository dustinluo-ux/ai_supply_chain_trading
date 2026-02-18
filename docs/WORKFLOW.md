# WORKFLOW — Canonical Execution Flow

**Last Updated:** 2026-02-14

This document defines **what happens**, in order. Implementation details live in `SYSTEM_MAP.md`. Architecture and data flow live in `ARCHITECTURE.md`.

---

## Canonical Workflow Stages

### 1. Load Configurations and Data

**Inputs:**
- Configuration files from `config/`
- Price data (OHLCV CSV files)
- Optional: news data JSON files
- SPY benchmark data
- Memory ledger (regime history)

**Operations:**
- Parse YAML configurations
- Load price data into DataFrames
- Index and validate date ranges

### 2. Enforce Invariants

**Critical checks:**
- No look-ahead in data slicing
- Schema validation (required OHLCV columns)
- Sufficient history for indicators (minimum lookback periods)
- Date continuity and timezone consistency

**Failure mode:** Terminate immediately if any invariant fails

### 3. Build Signals

**Signal Backend (dual architecture):**

SignalEngine switches backend based on execution mode:

- **Backtest mode:** 
  - Backend: `technical_library` + optional `news_engine`
  - Computes indicators fresh from price data
  - Master Score: category-weighted (Trend 40%, Momentum 30%, Volume 20%, Volatility 10%)
  - Optional News Alpha overlay if `--news-dir` provided

- **Weekly mode:**
  - Backend: Precomputed scores from `SignalCombiner.get_top_stocks()`
  - Loads pre-calculated signals from `data/signals/`
  - Same SignalEngine interface, different data source

**Technical signals:**
- Input: Historical price data sliced to `<= signal_date`
- Process: `SignalEngine` computes indicators and Master Score
- Output: Master Score per ticker (0-1 normalized)

**News overlay (optional):**
- Input: `data/news/{ticker}_news.json`
- Process: FinBERT sentiment + EventDetector
- Strategies: Buzz (A), Surprise (B), Sector Relative (C), Event-Driven (D)
- Output: News composite score (0-1 normalized)
- Blending: `final_score = 0.8 × technical + 0.2 × news` (configurable)

**Dynamic weighting (optional):**
- Modes: fixed, regime, rolling, ml
- Adjusts category weights (Trend/Momentum/Volume/Volatility)
- Safety: uses only T−1 or earlier data

### 4. Detect Market Regime

**Primary method:** 3-State Gaussian HMM on SPY returns
- States: BULL, BEAR, SIDEWAYS
- Mapping: by mean return (highest = BULL, lowest = BEAR, middle = SIDEWAYS)

**Fallback method:** SPY vs 200-day SMA
- SPY > 200-SMA → bullish regime
- SPY < 200-SMA → bearish regime

**Output:**
- Regime state label
- Transition matrix (logged on first Monday)
- Mean return and volatility per state

### 5. Apply Policy Gates

**Gates applied (backtest mode):**

| Gate | Condition | Action |
|------|-----------|--------|
| **CASH_OUT** | Regime = BEAR AND SPY < 200-SMA | 100% cash position |
| **Sideways scaling** | Regime = SIDEWAYS | Position size × 0.5 |
| **Daily risk exit** | Single-day return ≤ threshold (e.g. −5%) | Exit position (no reallocation) |

**Kill-switch guard:** CASH_OUT is only applied when regime_state is not None. If regime detection fails or returns None, the kill-switch branch is not applied.

**Mode differences:**
- **Backtest mode:** PolicyEngine applies full gates
- **Weekly execution mode:** Passthrough (no regime or gates applied)

### 6. Select Strategy Parameters

**Process:**
- Memory-aware parameter selection
- Safety checks on parameter ranges
- Validation against constraints

**Parameters include:**
- Top-N selection count
- Weight bounds (min/max per position)
- Risk thresholds
- Rebalance frequency

### 7. Construct Portfolio Intent

**Steps:**
1. **Rank:** Sort tickers by final score (descending)
2. **Select:** Choose top-N tickers
3. **Size:** Apply inverse-volatility weighting
   - Weight ∝ 1 / (ATR_norm + ε)
   - Uses ATR from Signal Day − 1 (no look-ahead)
4. **Normalize:** Scale weights to sum to 1.0

**Output:** Portfolio intent with target weights per ticker

### 8. Execute or Simulate

**Mode-dependent behavior:**

**Backtest mode:**
- Simulate trades at Next-Day Open
- Apply transaction costs (15 bps per trade)
- Track positions and returns
- Apply mid-week risk exits

**Dry-run mode:**
- Generate trade orders without execution
- Log intended trades for review

**Live/Paper mode:**
- Submit orders to IBKR via executor
- Monitor fill status
- Reconcile positions

### 9. Measure Performance

**Metrics calculated:**
- **Sharpe Ratio:** `(mean_return × 252) / (std_return × √252)`
- **Total Return:** Cumulative portfolio return
- **Maximum Drawdown:** Peak-to-trough decline
- **Win Rate:** Percentage of profitable periods

**Benchmark comparison:**
- SPY total return
- SPY Sharpe ratio
- Relative performance

### 10. Update Memory and Logs

**Post-run only (never mid-run):**

**Memory updates:**
- Performance CSV (optional)
- Regime ledger (planned, not yet implemented)
- Signal history

**Logging outputs:**
- Execution logs: `logs/`
- Backtest results: `outputs/backtest_master_score_*.txt`
- State tracking: `[STATE]` and `[REGIME]` log entries
- Audit trail (when enabled)

**Failure handling:**
- No partial-run memory corruption
- Atomic updates or rollback

---

## Research Spine — Mandatory Execution Contract

### Requirements

There must exist exactly **one canonical research spine per mode**.

The research spine must:

1. **Execute all modules** listed in SYSTEM_MAP.md in declared order
2. **Support only these modes:**
   - `backtest`
   - `weekly_dry_run`
   - `grid_search`
3. **Produce all outputs** declared in DECISIONS.md
4. **Fail loudly** if any declared output is missing or invalid

**Silent success is not permitted.**

### Run Manifest

Each spine run must emit a run manifest recording:
- Run mode
- Modules executed
- Outputs produced
- Timestamps
- Success/failure status

---

## Workflow Validation Checkpoints

### Pre-execution
- [ ] Configuration files loaded successfully
- [ ] All required data files present
- [ ] Date ranges valid and sufficient
- [ ] No timezone inconsistencies

### During execution
- [ ] No look-ahead violations
- [ ] All declared invariants hold
- [ ] Signals computed for all tickers
- [ ] Portfolio weights sum to 1.0
- [ ] Transaction costs applied

### Post-execution
- [ ] All declared outputs exist
- [ ] Performance metrics calculated
- [ ] Logs written successfully
- [ ] Memory updated atomically

---

## Mode-Specific Behavior Matrix

| Stage | Backtest | Weekly Dry-Run | Grid Search |
|-------|----------|----------------|-------------|
| **Load data** | Historical CSV | Latest + historical | Historical CSV |
| **Signal backend** | technical_library | SignalCombiner | technical_library |
| **Policy gates** | Full (CASH_OUT, scaling, exits) | Passthrough | Full |
| **Execution** | Simulated | None (logging only) | Simulated |
| **Output** | Full metrics + logs | Trade list + logs | Parameter sweep results |

---

## Invariant Enforcement

**Location:** Currently enforced locally within canonical entry points

**Planned:** Central invariant layer (v2 goal)

**Critical invariants:**
1. No future data in signal computation
2. Schema validation on all DataFrames
3. Minimum history requirements met
4. No NaN/Inf in final scores or weights
5. All declared outputs produced

**Failure mode:** Immediate termination with clear error message

---

## Single Source of Truth Principle

This workflow document is the authoritative reference for:
- Execution order
- Stage dependencies
- Mode-specific variations
- Output requirements

Any conflicts between this document and code should be resolved in favor of this document, with code updated accordingly.
