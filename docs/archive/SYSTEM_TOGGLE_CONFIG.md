# System Toggle and Configuration Audit

**Purpose:** How the two systems are configured and how to “toggle” between historical and live usage.  
**Verification date:** 2026-01-29  

---

## 1. Master Config That Switches Between Systems?

**No.** There is no single “master” config that turns “System 1” on and “System 2” off (or vice versa). Choice of system is **which script you run**:

- **System 1:** Run `python test_signals.py ...` → uses `config/data_config.yaml` and CSV universe; backtest only.
- **System 2:** Run `python run_weekly_rebalance.py ...` or `python run_e2e_pipeline.py ...` → uses `config/config.yaml` and `config/trading_config.yaml`; warm-up + signals + rebalance (dry-run or live).

No env var or YAML key like `system: 1|2` exists.

---

## 2. Independent Entry Points

- **System 1:** `test_signals.py` (and its args: `--universe-size`, `--top-n`, `--data-dir`).
- **System 2:** `run_weekly_rebalance.py` (`--dry-run` / `--live`, `--mode`, etc.), `run_e2e_pipeline.py` (`--no-warmup`, `--mode`).

They are independent: different scripts, different config files, different data paths. You “toggle” by running one script or the other.

---

## 3. Shared vs System-Specific Config Files

| File | Used by | Role |
|------|---------|------|
| **config/data_config.yaml** | System 1 (UniverseLoader, test_signals) | data_dir (stock_market_data), universe_selection, news_data |
| **config/config.yaml** | System 2 (run_weekly_rebalance, run_e2e) | data.date_range, signal_weights, backtest.portfolio_size, llm, news, etc. |
| **config/trading_config.yaml** | System 2 | trading.executor (mock vs ib), initial_capital |
| **config/signal_weights.yaml** | Both (if SignalCombiner loads it) | Weights for supply_chain_score, sentiment_momentum, price_momentum, volume_spike |
| **config/model_config.yaml** | ML / models | Model-related settings |
| **config/trading_config.yaml** | Execution | Executor type, capital |

So:

- **System 1** is driven by `data_config.yaml` (and any shared signal_weights).
- **System 2** is driven by `config.yaml` and `trading_config.yaml`.
- They **share** signal weights (e.g. in config.yaml or signal_weights.yaml) but **do not share** data dir or execution config.

---

## 4. How to Say “Use Historical” vs “Use Live Data”

- **System 1:** Always “historical” in practice: it reads from `data/stock_market_data/` (CSVs) and `data/news/`. There is no runtime switch to “live” in test_signals.py; it’s backtest-only.

- **System 2:**
  - **Historical vs recent (warm-up):**
    - **Use historical when available:** Ensure parquet files exist in `data/prices/` and call `warm_up(..., use_recent=False)` or run E2E with `--no-warmup` if you only want to use pre-built signals.
    - **Use recent/live data:** Use `warm_up(..., use_recent=True)` (default in run_e2e_pipeline) so last N days come from yfinance; for live execution set `trading_config.yaml` → `executor: ib` and run with `--live`.
  - **Config:** `config/config.yaml` → `data.date_range` defines the historical range used by warm-up; `trading_config.yaml` → `executor` and `run_weekly_rebalance.py --live` control live execution.

So:

- **“Use historical”:** System 1 = always; System 2 = parquet in `data/prices/` + optional `use_recent=False` or `--no-warmup`.
- **“Use live/recent”:** System 2 only: `use_recent=True` (warm-up) and/or `executor: ib` + `--live`.

---

## Summary

| Question | Answer |
|----------|--------|
| Master config that switches systems? | No; switch by which script you run. |
| Independent entry points? | Yes: test_signals.py vs run_weekly_rebalance.py / run_e2e_pipeline.py. |
| Shared config files? | Partially: signal_weights (or config.yaml weights) can be shared; data and execution configs are separate. |
| How to “use historical” vs “use live”? | S1 = always historical (CSV). S2 = historical via data/prices + use_recent flag; live via executor + --live. |

No naming conflicts: each system has a clear set of config files and entry points.
