# Backtest Execution & Portfolio Assumptions

This document records the **execution and portfolio construction** assumptions for the Technical Library Master Score backtest (`scripts/backtest_technical_library.py`). Indicator math is unchanged; only execution timing, costs, sizing, and systemic risk logic are described here.

---

## 1. Execution Timing

| Setting | Value | Description |
|--------|--------|-------------|
| **Execution** | **Next-Day Open** | Orders are assumed filled at the **Open of the first trading day after** the signal (weekly Monday close). This removes look-ahead bias: we do not use the Close of the signal day for entry. |
| **First-day return** | Open-to-Close | On the entry day, period return is `(Close − Open) / Open` for each position. |
| **Subsequent days** | Close-to-Close | For all other days in the holding period, period return is the usual close-to-close percent change. |

---

## 2. Transaction Costs (Friction)

| Setting | Value | Description |
|--------|--------|-------------|
| **Slippage + Commission** | **0.15% per trade** | A single friction cost of 15 bps is applied on each rebalance (entry/exit). Implemented as a deduction from portfolio return on rebalance dates. |
| **Location** | `FRICTION_BPS = 15` | Defined at top of `scripts/backtest_technical_library.py`; see `docs/BACKTEST_ASSUMPTIONS.md` for documentation. |

---

## 3. Position Sizing (Allocation)

| Setting | Value | Description |
|--------|--------|-------------|
| **Method** | **Inverse Volatility Weighting** | Weights are proportional to `1 / (ATR_norm + ε)` so higher-risk (higher ATR_norm) names get smaller allocations. |
| **Volatility proxy** | **ATR_norm** | From the Technical Library (`calculate_all_indicators`); normalized 0–1 over a rolling window. Used as the risk proxy for sizing. |
| **Normalization** | Sum to 1 | Raw inverse-volatility weights are scaled so that the active positions sum to 100%. |

---

## 4. Systemic Risk (Market Kill-Switch)

| Setting | Value | Description |
|--------|--------|-------------|
| **Benchmark** | **SPY** | Benchmark ticker for the kill-switch (configurable via `BENCHMARK_TICKER`). |
| **Condition** | SPY Close &lt; 200-day SMA | As of the signal date (Monday close), if the last available SPY close is below its 200-day simple moving average, the kill-switch is applied. |
| **Mode** | **Cash** (default) or **Half** | Controlled by `KILL_SWITCH_MODE`: `"cash"` → 100% cash (no equity exposure); `"half"` → position sizes reduced by 50%. |
| **When SPY missing** | Off | If SPY data is not available, the kill-switch is disabled and the strategy runs without it. |

---

## 5. Summary Table

| Assumption | Current value |
|------------|----------------|
| Execution time | Next-Day Open |
| Slippage/commission | 0.15% per trade |
| Position sizing | Inverse Volatility (ATR_norm) |
| Kill-switch | ON when SPY &lt; 200 SMA; mode: cash or half |

These settings are the single source of truth for friction, execution timing, and portfolio construction in the Technical Library backtest.

---

## 6. Critical Audit (Safety)

- **Signal lag:** Position × return uses **no `.shift(1)`**. `positions_df` is defined as weight at **start of day D**; we earn **return during D**. Entry is **Next-Day Open** (first trading day after Monday), so we never use Monday’s close with Monday’s signal — no look-ahead.
- **Mid-week exit:** **Daily risk check**: if a position’s single-day return ≤ `DAILY_EXIT_PCT` (e.g. −5%), that position is set to zero from that day to the end of the rebalance block. Entry remains Mondays-only; exit can occur any weekday.
- **Benchmark alignment:** SPY (close, SMA200) is **reindexed to the universe `all_dates`** with `ffill`; same timezone (tz-naive) as universe. Kill-switch uses last available SPY ≤ Monday to avoid timestamp leakage.
- **Safety report:** Run the backtest without `--no-safety-report` to print the Safety Report in the terminal after each run.

---

## 7. Path Dependency Safeguards

- **ATR sizing lag:** Inverse Volatility Weights use **ATR_norm from Signal Day − 1** (the trading day before the Monday signal), not the signal day. This avoids leaking same-day volatility into position size. In code: `row_sizing = ind.iloc[-2]` when `len(ind) >= 2`; `atr_norms[t]` is taken from `row_sizing`, not from `row = ind.iloc[-1]`.
- **Mid-week cash handling:** When a position hits `DAILY_EXIT_PCT` and is set to 0 for the rest of the rebalance block, we **do not reallocate** that weight to the remaining stocks. The exited weight is treated as cash (zero return). Portfolio return remains `sum(position_i * return_i)`; the sum of positions can drop below 1.0 after exits. We do **not** “teleport” cash from exited names into the remaining names mid-week.

**2022 stress test:** To run full-year 2022, use `--start 2022-01-01 --end 2022-12-31`. If the run is too heavy, run in four quarterly batches (Q1: 01-01 to 03-31, Q2: 04-01 to 06-30, Q3: 07-01 to 09-30, Q4: 10-01 to 12-31) and aggregate total return as `(1 + R_Q1) * (1 + R_Q2) * (1 + R_Q3) * (1 + R_Q4) - 1`.
