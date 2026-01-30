# Strategy Memory: Preventing Historical Amnesia

The system uses a **persistent regime ledger** and **Sortino-based audit** so live and backtest runs do not "forget" which strategies worked in which market states. This document explains how the ledger is used and how it prevents Historical Amnesia.

---

## 1. Regime Ledger (`data/logs/regime_ledger.csv`)

### Purpose

- **Persistent memory by market state:** Every time a strategy runs in a given regime (BULL, BEAR, SIDEWAYS), we append a row to the ledger with that regime, the strategy identifier, and the week’s return and drawdown.
- **Columns:** `Timestamp`, `Regime`, `Strategy_ID`, `Return`, `Max_Drawdown`.
- The file is created with headers on first use; rows are appended so history accumulates across runs.

### How It Is Written

- **`update_regime_ledger(regime, combination_id, weekly_return, weekly_drawdown)`** in `src/signals/performance_logger.py` appends one row.
- Call this at the end of each backtest/live week (or rebalance) with the current regime, the active strategy/combination ID (e.g. `nw0.2`, `nw0.2_horiz5_risk0.5`), and that week’s return and max drawdown.
- Default path: `data/logs/regime_ledger.csv` (overridable via `ledger_path`).

### Why It Matters

- Without the ledger, the Strategy Selector only sees recent or in-run performance and can “forget” that, for example, a more conservative strategy did better the last time the market was in BEAR.
- The ledger gives a **durable record** of “last time we were in this regime, strategy X had this return/drawdown,” so the selector can suggest switching when another strategy had a better Sortino in that regime.

---

## 2. Regime-Specific Sortino Ratio

### Definition

- **Sortino = (R_p - R_f) / σ_d**
- **σ_d** = downside deviation: only returns **below** the risk-free rate (or zero) are penalized.
- Implemented in **`calculate_regime_sortino(returns, risk_free_rate=0)`** in `src/signals/metrics.py`.

### BULL Regime Constraint

- For **BULL** regimes we **strictly ignore upside volatility**: only downside deviations enter σ_d.
- This avoids mistakenly throttling high-performing bull strategies when they have large positive returns; the Strategy Selector should not punish upside.

---

## 3. Integrated “Memory” Audit: `audit_past_performance`

### What It Does

- **`AdaptiveSelector.audit_past_performance(current_regime, current_strategy_id=None, current_sortino=None)`** in `src/signals/weight_model.py`:
  1. Reads `regime_ledger.csv` (or the configured `ledger_path`).
  2. Filters rows by **current_regime**.
  3. For each unique **Strategy_ID** in that regime, computes the **average Sortino** from the ledger’s return series (using `calculate_regime_sortino`).
  4. Logs a **Memory Alert** to the console, e.g.  
     `[MEMORY] Last time in BEAR, Strategy_X had a Sortino of 1.4. Current Strategy Sortino: 0.8. Suggesting switch...`

### When to Call It

- On each rebalance (e.g. every Monday), after determining the current regime and the strategy in use:
  - Compute the current strategy’s Sortino (e.g. from recent weekly returns or from the same ledger).
  - Call `audit_past_performance(current_regime, current_strategy_id="nw0.2", current_sortino=0.8)`.
- The log message reminds operators (and downstream logic) that **last time** we were in this regime, another strategy had better risk-adjusted performance, reducing “Historical Amnesia” during live and backtest runs.

---

## 4. End-to-End Flow

1. **Write memory:** At the end of each week, call **`update_regime_ledger(regime, strategy_id, weekly_return, weekly_drawdown)`** so the ledger grows over time.
2. **Read memory:** When entering a regime (e.g. on Monday), **`audit_past_performance(current_regime, current_strategy_id, current_sortino)`** scans the ledger for that regime and logs which strategy had the best historical Sortino and whether a switch is suggested.
3. **Select strategy:** Use **`get_optimal_weights(current_regime)`** (and optionally the Memory Alert) to choose or adjust the strategy for the coming period.

Together, the ledger and the audit ensure that **past regime-specific performance is not forgotten** and can explicitly suggest switching when a different strategy had better downside-adjusted returns the last time the market was in the same state.
