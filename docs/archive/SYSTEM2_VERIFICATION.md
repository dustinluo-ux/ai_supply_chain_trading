# System 2 Verification: Multi-Source Quant Pipeline (New)

**Purpose:** Live/recent data trading with multiple data sources.  
**Entry points:** `run_weekly_rebalance.py`, `run_e2e_pipeline.py`  
**Verification date:** 2026-01-29  

---

## 1. Can run_weekly_rebalance.py Run Without Affecting System 1?

**Yes.** System 2 does not modify System 1’s data or flow:

- **Price data:** System 2 uses `data/prices/*.parquet` (via warmup) and live feeds (yfinance, IBKR, Tiingo). It does **not** read or write `data/stock_market_data/*.csv`.
- **Entry point:** Only `run_weekly_rebalance.py` / `run_e2e_pipeline.py` invoke the weekly rebalance and E2E pipeline; `test_signals.py` is never called by them.
- **Config:** System 2 uses `config/config.yaml` and `config/trading_config.yaml`; System 1 uses `config/data_config.yaml` for universe and data dir.

Running `run_weekly_rebalance.py` or `run_e2e_pipeline.py` does not touch System 1’s CSV dir or backtest logic.

---

## 2. Separate Data Sources (System 2)

| Component | Role |
|-----------|------|
| **`src/data/warmup.py`** | Historical + recent merge: `load_historical()` from `data/prices/*.parquet`, `fetch_recent_yfinance()` for last N days, `merge_historical_recent()`. Optional `heal_append()` to append new bars to parquet. |
| **IBKR** | `src/data/ib_provider.py`: live market data, account info, real-time volume (Tick 8 × 100 for US equities). Used by PositionManager when executor is IB. |
| **Tiingo** | `src/data/news_sources/tiingo_source.py`: news API. Combined with Marketaux in `DualStreamNewsAggregator`. |
| **Marketaux** | Existing news source; dual-stream aggregator merges Marketaux + Tiingo. |
| **yfinance** | Warm-up recent data; cache init via `src/utils/yfinance_cache_init.py`. |

System 2 does **not** read from `data/stock_market_data/`; it uses `data/prices/` (parquet) and live APIs. No overwrite of original CSV files.

---

## 3. Own Signal Generation (Not Tied to System 1’s Gemini Backtest)

- **SignalCombiner:** Shared component. System 2 calls `SignalCombiner(data_dir="data", output_dir="data/signals")` and `get_top_stocks(date=..., top_n=..., mode=mode)` with `mode="technical_only"` or `"full_with_news"`.
- **Inputs for System 2:** SignalCombiner reads from `data/`:
  - `data/supply_chain_mentions.csv` (optional; if missing, supply_chain score is empty)
  - `data/sentiment_timeseries.parquet`
  - `data/technical_indicators.parquet`
- **Implication:** System 2 can run in **technical_only** mode using only technical indicators (and optionally sentiment/supply chain if those files exist). It does **not** depend on System 1’s inline backtest or on Gemini having been run in the context of `test_signals.py`; it only depends on the presence of the signal files under `data/` (typically produced by a separate pipeline, e.g. Phase 2 or a scheduled job).
- **Conclusion:** System 2 has its own entry points and data path; signal generation is shared code (SignalCombiner) but fed by different data (parquet/APIs) and can run without System 1’s Gemini backtest.

---

## 4. position_manager.py: Mock vs Live IBKR

- **Location:** `src/portfolio/position_manager.py`
- **Constructor:** `PositionManager(account_provider)` where `account_provider` is either:
  1. An object with `get_account_info()` (e.g. IB data provider), or  
  2. An executor with `get_positions()` and `get_account_value()` (e.g. mock or IB executor).
- **Adapter:** `_account_info_from_executor(executor)` builds the same `{margin_info, positions}` structure from executor so PositionManager works uniformly.
- **Usage in System 2:** `run_weekly_rebalance.py` uses `ExecutorFactory.from_config_file()` (from `config/trading_config.yaml`: `executor: mock` or `ib`) and passes the executor to `PositionManager(executor)`. So:
  - **Mock:** Executor returns in-memory positions/cash → delta trades computed without live broker.
  - **Live IBKR:** Executor (and optionally IB data provider) return real account/positions → delta trades for real rebalance.

**Verification:** PositionManager is agnostic to mock vs live; it only requires the provider interface. No code change needed to switch; only config (`trading_config.yaml` → `executor`).

---

## Summary

| Check | Status |
|-------|--------|
| run_weekly_rebalance.py does not affect System 1 | Yes |
| Uses warmup (historical + recent merge) | Yes |
| Uses IBKR / Tiingo / Marketaux / yfinance | Yes (no CSV dir) |
| Does not overwrite original CSVs | Yes |
| Own signal path (technical_only possible) | Yes (SignalCombiner + data/ signals) |
| position_manager works with mock and live IBKR | Yes (ExecutorFactory + adapter) |

System 2 is independent in terms of entry points, config, and data paths, and can run in parallel or sequentially with System 1 without conflicts.
