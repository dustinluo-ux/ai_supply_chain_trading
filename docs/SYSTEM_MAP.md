# SYSTEM_MAP — Workflow to Code Mapping

**Last Updated:** 2026-02-15  
**Parity Status:** 1:1 with disk (65 files in `src/`, 16 canonical scripts)

This document maps the WORKFLOW stages to executable code modules. This is the authoritative reference for understanding which code implements which logical step.

**Parity rule:** Every `.py` file under `src/` is listed here. If a file is not listed, it should not exist in `src/`.

---

## Canonical Entry Points

**Authoritative (production use):**
- `scripts/backtest_technical_library.py` — Master Score backtest with full feature support
- `scripts/research_grid_search.py` — Parameter sweep and optimization
- `scripts/run_execution.py` — Canonical execution entry (mock/paper)
- `scripts/run_weekly_rebalance.py` — Canonical automated rebalancing entry; delegates to `run_execution.py`; produces validated orders via last-close price injection (watchlist from `config/data_config.yaml`)

**Testing & Verification:**
- `scripts/verify_determinism.py` — P0 determinism gate (SHA256 comparison)
- `scripts/verify_environment.py` — Environment and dependency verification
- `scripts/test_target_weight_regression.py` — Spine regression test
- `scripts/test_execution_parity.py` — Backtest vs execution parity test

**Data Management:**
- `scripts/build_supply_chain_db.py` — Supply chain DB builder (per SUPPLY_CHAIN_DB.md)
- `scripts/expand_database_core_stocks.py` — Supply chain DB expansion (per SUPPLY_CHAIN_DB.md)
- `scripts/merge_news_chunks.py` — One-shot: merge flat + {ticker}_20*.json chunks into data/news/{ticker}_news.json (dedupe on title, sort by publishedAt; chunks left in place)
- `scripts/generate_daily_weights.py` — Task 6: daily target weights table (watchlist from data_config, compute_target_weights, CSV: date, ticker, target_weight, latest_close, notional_units)
- `scripts/daily_workflow.py` — Task 7: run update_price_data (with SPY), update_news_data, generate_daily_weights via subprocess; watchlist from data_config
- `scripts/sync_universe.py` — Sync 40-ticker universe from config/universe.yaml to data_config.yaml (watchlist, max_tickers); ensure trading_data/news/raw_bulk, historical_archives
- `scripts/check_data_integrity.py` — Read-only diagnostic: price CSV presence/start/gaps and news article counts from universe.yaml; table + summary

**Research / ML:**
- `scripts/train_ml_model.py` — Phase 3 ML training runner: train ridge model, evaluate Spearman IC on test period; save to models/saved/ only if IC ≥ 0.02 (no signal_engine wiring)

---

## Core Module Structure

### Single Spine Architecture: `src/core/` (7 files)

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | Re-exports PolicyEngine, PortfolioEngine, Intent, types, compute_target_weights |
| `config.py` | Environment-level config: load_dotenv, DATA_DIR, NEWS_DIR, TIINGO_API_KEY, MARKETAUX_API_KEY |
| `policy_engine.py` | Regime detection and policy gate application (CASH_OUT, sideways scaling) |
| `portfolio_engine.py` | Portfolio construction and intent generation (rank, top-N, inverse-vol) |
| `target_weight_pipeline.py` | Canonical spine: SignalEngine → PolicyEngine → PortfolioEngine |
| `intent.py` | Portfolio intent data structures (`Intent` dataclass) |
| `types.py` | Shared type aliases (`DataContext`, `Context`) |

**Note:** `SignalEngine` lives in `src/signals/signal_engine.py` (not in `src/core/`) to avoid circular imports. See `src/core/__init__.py` L5–6.

### Signal Generation: `src/signals/` (9 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `signal_engine.py` | **Canonical SignalEngine** — orchestrates backtest + weekly signal generation, sentiment propagation, regime auto-detection |
| `technical_library.py` | Master Score computation, all indicator calculation (pandas_ta), normalization |
| `news_engine.py` | News Alpha strategies (Buzz, Surprise, Sector, Event), FinBERT, EventDetector |
| `weight_model.py` | Dynamic category weighting (fixed/regime/rolling/ml), HMM regime detection, AdaptiveSelector |
| `signal_combiner.py` | Legacy combined signal generation (weekly/precomputed path only) |
| `sentiment_propagator.py` | Tier 1/Tier 2 supply chain sentiment propagation (per STRATEGY_LOGIC.md §2.1) |
| `performance_logger.py` | Weekly performance CSV logging, regime ledger management |
| `metrics.py` | Regime-aware Sortino ratio calculation |

### Data Layer: `src/data/` (15 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `base_provider.py` | Abstract `BaseDataProvider` interface |
| `csv_provider.py` | CSV/Parquet price data provider |
| `provider_factory.py` | `DataProviderFactory` — creates CSV or IB providers |
| `ib_provider.py` | IBKR data provider (TWS via ib_insync) |
| `price_fetcher.py` | Historical price data ingestion (yfinance, parquet) |
| `news_fetcher.py` | News data ingestion |
| `news_base.py` | Abstract base class for news sources |
| `news_fetcher_factory.py` | News source factory |
| `universe_loader.py` | Ticker universe loading from config |
| `base_loader.py` | Abstract `BaseDataLoader` class |
| `supply_chain_manager.py` | Supply chain DB read/write/freshness tracking |
| `sec_filing_parser.py` | SEC 10-K filing parser for supply chain extraction |
| `apple_supplier_list.py` | Apple official supplier list download/parsing |

**News Sources:** `src/data/news_sources/` (6 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `base_provider.py` | Abstract NewsProvider (fetch_history, fetch_live, standardize_data) — provider-agnostic interface |
| `marketaux_source.py` | Marketaux news API |
| `alphavantage_source.py` | AlphaVantage news API |
| `finnhub_source.py` | Finnhub news API |
| `newsapi_source.py` | NewsAPI source |

### Portfolio Management: `src/portfolio/` (2 files)

| Module | Purpose |
|--------|---------|
| `position_manager.py` | Position tracking, delta trade calculation, rebalancing |
| `position_sizer.py` | **Stage 4** ATR-based position sizing: $Position = (Equity × Risk) / (ATR × Multiplier)$; config: `trading_config.position_sizing` |

### Execution: `src/execution/` (7 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `base_executor.py` | Abstract `BaseExecutor` interface |
| `mock_executor.py` | Mock executor for backtesting (no real orders) |
| `ib_executor.py` | IBKR executor (paper + live) |
| `executor_factory.py` | `ExecutorFactory` — creates mock/IB executors |
| `fill_ledger.py` | Persistent fill ledger: append_fill_record(), read_fill_ledger(); outputs/fills/fills.jsonl |
| `ibkr_bridge.py` | LiveExecutionBridge: AccountMonitor, RiskManager, OrderDispatcher, CircuitBreaker, RebalanceLogic (per LIVE_EXECUTION_BRIDGE_DESIGN.md) |

**Spine integration:** `scripts/run_execution.py` builds a last-close price Series from `prices_dict` and passes it as `prices` into `PositionManager.calculate_delta_trades` so dry-run/mock produces correct share quantities (execution parity; see DECISIONS.md D018).

### ML Models: `src/models/` (6 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `base_predictor.py` | Abstract base predictor interface |
| `linear_model.py` | Linear/Ridge/Lasso regression predictor |
| `tree_model.py` | XGBoost gradient boosting predictor |
| `model_factory.py` | Model factory (creates predictor by type) |
| `train_pipeline.py` | Training pipeline with TimeSeriesSplit CV |

### Backtesting: `src/backtest/` (2 files)

| Module | Purpose | Note |
|--------|---------|------|
| `__init__.py` | Package marker | |
| `backtest_engine.py` | vectorbt-based backtest engine | Non-canonical; canonical backtest is `scripts/backtest_technical_library.py` |

### Evaluation: `src/evaluation/` (2 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `performance_tracker.py` | Task 7: PerformanceTracker.run(signals_csv, data_dir) — equity curves from daily signals, total_return, spy_return, alpha, max_drawdown, sharpe |

### Utilities: `src/utils/` (9 files)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package marker |
| `config_manager.py` | Centralized YAML config loading (AI_RULES §10 enforcement) |
| `storage_handler.py` | Parquet I/O: save_to_parquet(), read_from_parquet() (pyarrow) |
| `logger.py` | Logging configuration (`setup_logger()`) |
| `defensive.py` | Invariant checks, guards, safe file operations, `safe_read_yaml` |
| `ticker_utils.py` | Ticker manipulation helpers |
| `trading_parameters.py` | Trading parameter defaults and helpers |
| `client_id_rotation.py` | IBKR client ID rotation (avoid conflicts) |
| `yfinance_cache_init.py` | yfinance cache initialization |

### Package Root (1 file)

| Module | Purpose |
|--------|---------|
| `src/__init__.py` | Top-level package marker |

---

## Workflow Stage → Module Mapping

### Stage 1: Load & Invariants

**Workflow:** Load configs and data, enforce invariants

**Code:**
- Entry: `scripts/backtest_technical_library.py`
- Config loading: `src/utils/config_manager.py` → `get_config()` reads all YAML files
- Price loading: `load_config()` + `load_prices()` in entry points (planned: centralize in `src/data/csv_provider.py`)
- Invariants: `src/utils/defensive.py` → validation functions

**Key functions:**
```python
get_config() → ConfigManager
cfg.get_param("data_config.data_sources.data_dir") → value
load_config() → dict
load_prices(data_dir, tickers) → dict[str, DataFrame]
find_csv_path(data_dir, ticker) → Path
ensure_ohlcv(df) → DataFrame
```

### Stage 2: Signals

**Workflow:** Build signals (technical + optional news + optional propagation)

**Code paths by mode (dual backend architecture):**

**Backtest mode:**
- Module: `src.signals.signal_engine.SignalEngine`
- Backend: `src.signals.technical_library` + optional `src.signals.news_engine`
- Optional: `src.signals.sentiment_propagator` (when `enable_propagation=True`)
- Three-phase process:
  1. Phase 1: `calculate_all_indicators(df)` → normalized indicators; `compute_news_composite(...)` → direct news
  2. Phase 2: `SentimentPropagator.propagate(...)` → enriches news composites (optional)
  3. Phase 3: `compute_signal_strength(row, news_composite=...)` → Final Score

**Weekly mode:**
- Module: `src.signals.signal_engine.SignalEngine` (same interface)
- Backend: `src.signals.signal_combiner.SignalCombiner`
- Process: Loads pre-calculated signal outputs from `data/signals/`

**Key functions:**
```python
SignalEngine.generate(as_of_date, universe, data_context) → (scores, aux)
calculate_all_indicators(df: DataFrame) → DataFrame
compute_signal_strength(row, ...) → (master_score, result_dict)
compute_news_composite(news_dir, ticker, as_of, ...) → dict
SentimentPropagator.propagate(news_item) → List[PropagatedSignal]
```

### Stage 3: Regime & Policy

**Workflow:** Detect regime, apply policy gates

**Regime detection:**
- Module: `src.signals.weight_model` → `get_regime_hmm()`
- Auto-detection: `SignalEngine._detect_regime()` (HMM → SMA-200 fallback)
- States: BULL, BEAR, SIDEWAYS

**Policy application:**
- Module: `src.core.policy_engine.PolicyEngine`
- Method: `PolicyEngine.apply()` → `_apply_backtest()` (canonical)
- Gates: CASH_OUT (dual confirmation), sideways scaling (×0.5)

**Key functions:**
```python
get_regime_hmm(close_series, as_of_date, min_obs=60, n_components=3) → (state_label, info_dict)
PolicyEngine.apply(as_of_date, scores, aux, context) → (gated_scores, flags)
```

### Stage 4: Dynamic Weighting (Optional)

**Workflow:** Adjust category weights based on regime/optimization/ML

**Code:**
- Module: `src.signals.weight_model`
- Regime resolution: `SignalEngine._resolve_regime_weights()` (via ConfigManager)

| Mode | Engine | Function |
|------|--------|----------|
| `fixed` | Config YAML | Static weights from `technical_master_score.yaml` |
| `regime` | hmmlearn | `get_regime_hmm(...)` → BULL/BEAR/SIDEWAYS weights |
| `rolling` | PyPortfolioOpt | `get_optimized_weights(...)` |
| `ml` | Scikit-Learn | `get_ml_weights(...)` |

### Stage 5: Portfolio Intent & Position Sizing

**Workflow:** Rank, select top-N, compute sizes (Stage 4 sizing + regime exposure cap)

**Code:**
- Module: `src.core.portfolio_engine.PortfolioEngine`
- Method: `PortfolioEngine.build()` → `_build_backtest()`
- Sizing: `src.portfolio.position_sizer` — ATR-based weights; config: `config/trading_config.yaml` → `position_sizing.risk_pct`, `position_sizing.atr_multiplier`
- Regime cap: When `regime == BEAR`, target_exposure = 0.0 (backtest: `scripts/backtest_technical_library.py`)
- Supporting: `src.portfolio.position_manager`

**Process:**
1. Rank tickers by gated score (descending)
2. Select top N
3. **Stage 4:** Compute ATR-based weights via `position_sizer.compute_weights()` (or inverse-vol fallback in PortfolioEngine)
4. If regime == BEAR: set all weights to 0
5. Normalize to sum = 1.0 (or 0 when BEAR)

### Stage 6: Execution Layer

**Workflow:** Execute trades (simulate or live)

**Code:**
- Factory: `src.execution.executor_factory.ExecutorFactory`
- Executors: `src.execution.mock_executor.MockExecutor`, `src.execution.ib_executor.IBExecutor`

| Executor | Use Case | Module |
|----------|----------|--------|
| Mock | Backtesting | `mock_executor.py` |
| IB Paper | Paper trading | `ib_executor.py` (paper account) |
| IB Live | Live trading | `ib_executor.py` (live account) |

### Stage 7: Metrics & Memory

**Workflow:** Calculate performance, update logs and memory

**Code:**
- Metrics: Computed inline in `scripts/backtest_technical_library.py` (Sharpe, total return, max drawdown)
- Logging: `src.signals.performance_logger` (weekly CSV, regime ledger)
- Sortino: `src.signals.metrics.calculate_regime_sortino()`
- Output: `outputs/backtest_master_score_*.txt`

---

## Module Dependencies

### Import Hierarchy

```
scripts/backtest_technical_library.py
    ↓
src/signals/signal_engine.py (SignalEngine)
    ↓
src/signals/technical_library.py
src/signals/news_engine.py (optional)
src/signals/sentiment_propagator.py (optional)
    ↓
src/signals/weight_model.py (optional, regime/rolling/ml)
    ↓
src/core/policy_engine.py
    ↓
src/core/portfolio_engine.py
    ↓
src/execution/ (mock or IB)
```

### Configuration Files

| Config File | Purpose | Used By |
|-------------|---------|---------|
| `config/data_config.yaml` | Data source paths, universe, watchlist | `config_manager.py`, entry points |
| `config/technical_master_score.yaml` | Indicator weights, news_weight, regime weights | `technical_library.py`, `signal_engine.py` |
| `config/signal_weights.yaml` | Legacy signal weights | `signal_combiner.py` (non-canonical path) |
| `config/trading_config.yaml` | Execution parameters, IB config | `executor_factory.py` |
| `config/model_config.yaml` | ML model selection and training params | `src/models/` |
| `config/strategy_params.yaml` | Propagation, warmup, execution params | `config_manager.py` |

---

## Execution Mode Matrix

| Mode | Entry Point | Signal Backend | Policy Gates | Execution |
|------|-------------|----------------|--------------|-----------|
| **Backtest** | `backtest_technical_library.py` | `technical_library` + `news_engine` + `propagator` | Full | Simulated (inline) |
| **Grid Search** | `research_grid_search.py` | `technical_library` | Full | Simulated |
| **Execution** | `run_execution.py` | Same spine (via `target_weight_pipeline`) | Full | Mock or IB Paper |
| **Weekly Dry-Run** | (Planned) | `SignalCombiner` | Passthrough | None (log only) |
| **Paper Trading** | (Planned) | Same spine | Full | IB Paper |
| **Live Trading** | (Planned) | Same spine | Full | IB Live |

---

## File Count Summary

| Location | Files |
|----------|-------|
| `src/core/` | 7 |
| `src/signals/` | 9 |
| `src/data/` | 15 |
| `src/data/news_sources/` | 6 |
| `src/portfolio/` | 2 |
| `src/execution/` | 7 |
| `src/models/` | 6 |
| `src/backtest/` | 2 |
| `src/evaluation/` | 2 |
| `src/utils/` | 9 |
| `src/__init__.py` | 1 |
| **Total `src/`** | **65** |
| `scripts/` (canonical) | 16 |

---

## Non-Canonical Code

All non-canonical code has been relocated to `graveyard/`. See `graveyard/ARCHIVE_MAP.md` for a searchable index. Per AI_RULES.md §3 and §5.2, archived code is read-only reference material — search ARCHIVE_MAP.md before implementing new utilities.

---

This mapping is the authoritative reference for understanding code organization. Any code not listed here should be considered non-canonical unless explicitly added through the proper governance process.
