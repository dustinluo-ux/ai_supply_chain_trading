# Progress Report: Paper Trading & Live Execution Readiness

**Scope:** Evidence-based assessment using the **physical folder (filesystem)** as the source of truth.

**Important:** The repo intentionally excludes data and other sensitive content (e.g. `.gitignore`: `data/`, `outputs/`, `backtests/`, `*.csv`, `*.parquet`, etc.). This analysis reads the **actual directory on disk**, not the version-controlled file set. Paths and status below reflect what exists in the project folder.

---

## 1) Physical Folder Map

### Top-level (on disk)

| Path | Present on disk | Role |
|------|------------------|------|
| **config/** | Yes | Strategy, data, model, signal weights, trading YAML |
| **data/** | Yes | Generated/cached: cache, cache_backup, news, prices, raw, signals, stock_market_data |
| **docs/** | Yes | Documentation |
| **logs/** | Yes | Application logs |
| **outputs/** | Yes | Backtest logs (e.g. backtest_log_*.txt) |
| **backtests/** | Yes | results/ subfolder |
| **scripts/** | Yes | One-off / diagnostic scripts |
| **src/** | Yes | Core library (see below) |
| **run_phase1_test.py** | Yes | Phase 1: test price fetcher, news fetcher, LLM analyzer |
| **run_phase2_pipeline.py** | Yes | Phase 2: signal generation |
| **run_phase3_backtest.py** | Yes | Phase 3: backtest + reports |
| **run_strategy.py** | Yes | End-to-end: Phase 1 → 2 → 3 |
| **run_technical_backtest.py** | Yes | Technical-only backtest, weekly signals in memory |
| **download_*.py** | Yes | Price/news download scripts |
| **.env** | Yes (on disk) | Environment / API keys (repo-excluded) |

### src/ on disk (including repo-excluded subpackages)

| Path | Present on disk | Role |
|------|------------------|------|
| **src/data/** | Yes | Data layer (repo-excluded or in .gitignore) |
| **src/models/** | Yes | ML training / prediction (repo-excluded or in .gitignore) |
| **src/backtest/** | Yes | Backtest engine |
| **src/backtesting/** | Yes | Portfolio / PnL simulators |
| **src/execution/** | Yes | Mock + IBKR executor, factory |
| **src/signals/** | Yes | Signal generation |
| **src/portfolio/** | Yes | Position sizing |
| **src/risk/** | Yes | Risk calculator |
| **src/policies/** | Yes | Exit policies, signal mapper |
| **src/regimes/** | Yes | Macro classifier |
| **src/logging/** | Yes | Audit logger |
| **src/utils/** | Yes | Logger, defensive, ticker utils |

### src/data/ on disk (physical listing)

| File | Role |
|------|------|
| **__init__.py** | Package init |
| **price_fetcher.py** | PriceFetcher: Russell 2000, market cap filter, yfinance → parquet; `run()`, `fetch_all_tickers()`, `get_existing_tickers()` |
| **news_fetcher.py** | Wrapper: NewsFetcher via NewsFetcherFactory (config-driven) |
| **news_fetcher_factory.py** | NewsFetcherFactory: create_source(), create_from_config(); NewsFetcher class |
| **news_base.py** | Base for news sources |
| **ib_provider.py** | IBDataProvider: connect, get_historical_data, get_current_price, get_account_info(), cache |
| **provider_factory.py** | DataProviderFactory: create('csv'\|'ib'), from_config_file() |
| **base_provider.py** | BaseDataProvider |
| **csv_provider.py** | CSVDataProvider |
| **supply_chain_manager.py** | SupplyChainManager: load/save JSON DB, ensure_coverage, get_suppliers/get_customers |
| **universe_loader.py** | UniverseLoader |
| **sec_filing_parser.py** | SECFilingParser (used by build_supply_chain_db) |
| **apple_supplier_list.py** | download_apple_suppliers, get_us_listed_suppliers |
| **base_loader.py** | Base loader |
| **multi_source_factory.py** | Multi-source factory |
| **news_sources/alphavantage_source.py** | AlphaVantage news |
| **news_sources/finnhub_source.py** | Finnhub news |
| **news_sources/marketaux_source.py** | Marketaux news |
| **news_sources/newsapi_source.py** | NewsAPI news |

### src/models/ on disk (physical listing)

| File | Role |
|------|------|
| **__init__.py** | Package init |
| **train_pipeline.py** | ModelTrainingPipeline: prepare_training_data(), train, feature extraction, train/test split |
| **model_factory.py** | create_model() |
| **base_predictor.py** | BaseReturnPredictor |
| **linear_model.py** | Linear model |
| **tree_model.py** | Tree model |

---

## 2) End-to-End Workflow (Physical Folder)

### Market data ingestion

| Block | Status | Evidence (physical paths) | Risk |
|-------|--------|----------------------------|------|
| **Prices** | Implemented | `src/data/price_fetcher.py`: PriceFetcher, `run()`, `fetch_all_tickers()`, yfinance → `data/prices/*.parquet` | None |
| **News** | Implemented | `src/data/news_fetcher.py` → NewsFetcherFactory; `src/data/news_sources/` (alphavantage, finnhub, marketaux, newsapi); config-driven source | API keys / rate limits |
| **Fundamentals / supply chain DB** | Implemented | `src/data/supply_chain_manager.py`; scripts use `sec_filing_parser`, `apple_supplier_list` | DB file path: `data/supply_chain_relationships.json` (under data/) |

### Supply-chain DB and propagation

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **DB build** | Implemented | `scripts/build_supply_chain_db.py` uses `src.data.sec_filing_parser`, `src.data.apple_supplier_list`; writes `supply_chain_relationships.json` | Depends on data/ being present on disk |
| **DB consumption** | Implemented | `src/signals/sentiment_propagator.py`: SupplyChainManager(db_path), tiered propagation | Same |
| **Scanner (LLM)** | Implemented | `src/signals/supply_chain_scanner.py`: LLMAnalyzer, reads news JSON, writes supply_chain_mentions | Requires news data |

### Feature engineering & signals

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **Technical indicators** | Implemented | `src/signals/technical_indicators.py`: momentum, volume spike, RSI; writes `technical_indicators.parquet` | Needs price parquet in data/prices |
| **Sentiment time series** | Implemented | `src/signals/sentiment_analyzer.py`: FinBERT/keyword, rolling; expects data/news | Same |
| **Signal combiner** | Implemented | `src/signals/signal_combiner.py`: combine_signals(), get_top_stocks(), technical_only path; writes `top_stocks_{date|latest}.csv` | As in previous report: Phase 3 may reuse single “latest” file if date files missing |

### Model inference (ML path)

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **Training pipeline** | Implemented | `src/models/train_pipeline.py`: ModelTrainingPipeline, prepare_training_data(), config from `config/model_config.yaml` | Not wired into run_phase* or run_strategy in reviewed code |
| **Model factory** | Implemented | `src/models/model_factory.py`, linear/tree/base_predictor | Same |

### Portfolio construction & backtest

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **Backtest engine** | Implemented | `src/backtest/backtest_engine.py`: load_price_data, load_signals, generate_weekly_signals, apply_stop_loss, run_backtest, compare_to_benchmark | Phase 3: weekly signals from files; if only “latest” exists, same ranking every week |
| **Technical-only backtest** | Implemented | `run_technical_backtest.py`: builds weekly signals in memory per Monday via SignalCombiner.get_top_stocks(date=...) | No file-dependency lookahead |
| **Sizing / risk** | Implemented | `src/portfolio/sizing.py`, `src/risk/risk_calculator.py`; not used inside BacktestEngine | Backtest uses equal weight only |

### Execution (IBKR)

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **IB data provider** | Implemented | `src/data/ib_provider.py`: IBDataProvider, _connect(), get_account_info() (margin_info, positions) | Requires TWS/Gateway running |
| **IB executor** | Implemented | `src/execution/ib_executor.py`: submit_order, cancel_order, get_positions, get_account_value (via ib_provider) | Same |
| **Executor factory** | Implemented | `src/execution/executor_factory.py`: create('mock'\|'ib_paper'\|'ib_live'), from_config_file(); uses DataProviderFactory for IB | Config: trading_config.yaml |
| **Paper/live runner** | Missing | No script found that: generates signals for “this week” → computes target positions → creates executor → submits orders | No one-shot paper/live rebalance entrypoint |

### Rebalance scheduling

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **In backtest** | Implemented | Weekly (W-MON) in BacktestEngine and run_technical_backtest | As above (signal file vs in-memory) |
| **Cron / scheduler** | Missing | No cron, APScheduler, or “run weekly” entrypoint for paper/live | Manual runs only |

### Persistence & logging

| Block | Status | Evidence | Risk |
|-------|--------|----------|------|
| **Config** | Implemented | config/*.yaml (config, data_config, model_config, signal_weights, trading_config) | Reproducibility if configs versioned |
| **Audit logger** | Implemented | `src/logging/audit_logger.py`: log_audit_record() → outputs/audit/ | Not called from run_phase* in reviewed code |
| **Outputs on disk** | Present | outputs/ contains backtest_log_*.txt; data/ has prices, news, signals, cache | data/ and outputs/ repo-excluded |

---

## 3) Backtesting Quality (Unchanged)

- **Time horizon:** From config `data.date_range`; engine uses start/end.
- **Metrics:** total_return, sharpe_ratio, max_drawdown, win_rate (daily), num_trades, benchmark (SPY).
- **Risks:** (1) Phase 3 relies on per-Monday signal files; fallback to “latest” reuses same ranking. (2) Parameter sensitivity in run_phase3_backtest does not run backtests (stub). (3) Win rate is daily, not trade-level. (4) Survivorship not explicitly handled.

---

## 4) Execution Readiness (Physical Folder)

### IBKR – what exists on disk

- **src/data/ib_provider.py:** Connect (host, port, client_id), get_historical_data (with cache), get_current_price, get_account_info() (margin_info, positions).
- **src/execution/ib_executor.py:** submit_order (Market/Limit), cancel_order, get_positions, get_account_value.
- **config/trading_config.yaml:** executor, paper_account, live_account, ib host/port/client_id.

### Missing for paper trading

1. **Orchestration script:** A single script that (a) generates signals for “this week” or latest, (b) computes target portfolio (e.g. equal weight top N), (c) loads ExecutorFactory.from_config_file() or create('ib_paper', ...), (d) gets current positions, (e) computes deltas and submits orders. Not present on disk.
2. **Fill reconciliation:** No comparison of expected vs actual positions after submit.
3. **Scheduling:** No automated weekly run.

### Missing for live trading

- Same as paper; plus: no use of config order/position limits in code; no idempotency or duplicate-order guardrails.

---

## 5) TODO/FIXME Scan (Unchanged)

- `src/signals/gemini_analyzer.py` line 18: TODO migrate to google.genai.
- `docs/archive/MODEL_REGISTRY.md`: TODO add LSTM/GRU.

---

## 6) Readiness Checklists (Revised for Physical Folder)

### Must-have for paper trading

| # | Requirement | Status | Where (physical) / gap |
|---|-------------|--------|--------------------------|
| 1 | Price data for universe | Implemented | `src/data/price_fetcher.py`, `data/prices/` |
| 2 | News data (optional for technical-only) | Implemented | `src/data/news_fetcher.py`, news_sources/, `data/news/` |
| 3 | Signal generation for “this week” | Implemented | SignalCombiner.get_top_stocks(date=...) |
| 4 | IBKR paper connection & account info | Implemented | `src/data/ib_provider.py`, get_account_info() |
| 5 | Submit/cancel orders, get positions | Implemented | `src/execution/ib_executor.py` |
| 6 | Config for paper | Implemented | config/trading_config.yaml |
| 7 | **Single script: signals → orders → submit** | **Missing** | No run_paper_rebalance.py (or equivalent) on disk |

### Must-have for live trading

- Same as paper; plus: live_account and port 7496 in config; safety limits and reconciliation not implemented in code.

---

## 7) Summary (Revised)

### 5 biggest risks

1. **Phase 3 backtest signal design** — If only `top_stocks_latest.csv` exists, the same ranking is reused every week (lookahead/stationarity). Prefer run_technical_backtest-style weekly signals in memory.
2. **No paper/live orchestration** — All execution and data pieces exist on disk (IBDataProvider, IBExecutor, PriceFetcher, NewsFetcher, SignalCombiner), but no script wires “signals → target positions → executor → submit”.
3. **Parameter sensitivity stub** — run_parameter_sensitivity() does not run backtests; sensitivity results are placeholders.
4. **No fill reconciliation or safety limits** — Config has execution limits; they are not enforced in executor or a wrapper.
5. **ML pipeline not wired to run_phase* / run_strategy** — src/models/ exists and is configured (model_config.yaml) but not invoked from the main entrypoints in the reviewed code.

### 5 fastest wins (≤2 hours each)

1. **Add run_paper_rebalance.py** — Load config → set date (e.g. today or last trading day) → run SignalCombiner.get_top_stocks(date=...) (technical_only or full) → compute equal-weight target for top N → ExecutorFactory.from_config_file() → get_positions() → compute delta orders → submit_order() for each. One manual run to validate chain.
2. **Wire Phase 3 to weekly signals in memory** — In run_phase3_backtest.py, for each Monday call SignalCombiner.get_top_stocks(date=monday_str, ...) and build positions from that (like run_technical_backtest.py), instead of relying on pre-generated per-date signal files.
3. **Wire audit logging** — Call log_audit_record() from run_phase3_backtest.py (and optionally run_strategy.py) after each run.
4. **Use execution limits from config** — In the paper script or executor wrapper, read min_order_size / max_position_size from trading_config.yaml and cap quantities before submit_order().
5. **Simple fill check** — In the paper script, after submitting orders: sleep briefly, get_positions(), compare to expected positions, log differences.

### Recommended 2-week execution plan

| Week | Focus | Actions |
|------|--------|--------|
| **Week 1** | **Backtest integrity & audit** | (1) Fix Phase 3 to generate weekly signals in memory. (2) Run technical-only backtest end-to-end; confirm metrics. (3) Wire audit logging. (4) Optionally wire ModelTrainingPipeline into a separate “train and score” script or Phase 2.5. |
| **Week 2** | **Paper execution** | (1) Add run_paper_rebalance.py (signals → target → executor → submit). (2) One manual paper run with TWS/Gateway; verify orders and positions. (3) Add config-based order/position limits and simple fill check. (4) Document in README: physical folder layout, that data/ and src/data/ exist on disk but are repo-excluded, and how to run paper rebalance. |

---

*Report generated from the **physical project folder** (filesystem). The repo intentionally excludes data and sensitive paths; this analysis does not use the repo as the sole roadmap.*
