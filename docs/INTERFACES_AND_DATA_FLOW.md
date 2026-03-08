# Interfaces and Data Flow — Structure, Contracts, Rationale

**Scope:** Design-only. No implementation code. Defines interfaces, data contracts, and data flow using the existing module structure.

**References:** `ARCHITECTURE.md`, `SYSTEM_MAP.md`, `src/core/types.py`, `src/core/intent.py`.

---

## 1. Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Spine is the single path** | All target-weight computation flows: SignalEngine → PolicyEngine → PortfolioEngine. One contract for backtest and execution. |
| **Context objects are caller-shaped** | `DataContext` and `Context` are dict-like; shape is defined by the caller (backtest vs weekly). Engines accept and pass through; they do not own the schema. |
| **Factories own concrete types** | Only factories (model_factory, executor_factory, provider_factory, news_fetcher_factory) know concrete classes. Callers depend on abstract interfaces. |
| **Intent is the execution contract** | `Intent` is the sole output of the spine that execution/backtest consume. No ad-hoc weight dicts downstream. |

---

## 2. Module Boundaries and Roles

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SCRIPTS (entry points)                                                       │
│  backtest_technical_library.py | run_weekly_rebalance.py | run_execution.py  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
┌──────────────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│  DATA LAYER               │  │  CORE SPINE      │  │  EXECUTION / PORTFOLIO   │
│  (providers, loaders)    │  │  (target weight  │  │  (intent → orders)       │
│  Opaque to spine         │  │   pipeline)      │  │  Consumes Intent         │
└──────────────────────────┘  └─────────────────┘  └─────────────────────────┘
         │                              │                        │
         │  prices_dict, news, config   │  DataContext, Context  │  Intent
         └──────────────────────────────┴────────────────────────┘
```

- **Data layer:** Supplies raw or precomputed inputs. Spine does not know *how* data was obtained.
- **Core spine:** Transforms (universe + data context) → scores → gated scores → Intent.
- **Execution/portfolio:** Consume Intent; produce orders and fills. Do not re-open signal logic.

---

## 3. Core Types (Existing Contracts)

### 3.1 DataContext (`src/core/types.py`)

| Contract | Description |
|----------|-------------|
| **Type** | `dict[str, Any]` (caller-defined shape) |
| **Purpose** | Everything needed for signal generation for one invocation. |
| **Typical keys (backtest)** | `prices_dict`, `news_dir` or `news_signals`, `spy_bench`, `config` bits, optional `precomputed_indicators`. |
| **Typical keys (weekly)** | `source: "precomputed"`, plus whatever SignalCombiner needs (paths, combiner instance). |
| **Owner** | Caller (script or pipeline). Engine reads only; does not mutate. |
| **Rationale** | Single argument for SignalEngine; allows different backends (technical_library vs precomputed) without changing the engine signature. |

### 3.2 Context (`src/core/types.py`)

| Contract | Description |
|----------|-------------|
| **Type** | `dict[str, Any]` (caller-defined shape) |
| **Purpose** | Everything needed for policy and portfolio for one invocation. |
| **Typical keys** | `regime_state`, `spy_below_sma200`, `sideways_risk_scale`, `top_n`, `weight_mode`, `ledger_path`, `kill_switch_active`, `kill_switch_mode`. |
| **Owner** | Caller / target_weight_pipeline. PolicyEngine and PortfolioEngine read only. |
| **Rationale** | Decouples regime/policy knobs from signal generation; same PolicyEngine applies whether regime came from HMM or SMA fallback. |

### 3.3 Intent (`src/core/intent.py`)

| Contract | Description |
|----------|-------------|
| **Type** | Dataclass: `tickers: list[str]`, `weights: dict[str, float]`, `mode: str`, `metadata: Optional[dict]` |
| **Invariants** | `weights` key set ⊆ `tickers`; when trading, weights sum to 1.0; when CASH_OUT, weights all 0. |
| **Produced by** | PortfolioEngine.build() |
| **Consumed by** | Backtest (signals_df row / position updates), run_execution (optimal_weights_series → PositionManager → delta trades → executor). |
| **Rationale** | Single canonical “target portfolio” object; no parallel code paths that build weights differently. |

---

## 4. Spine Interfaces (Contracts Only)

### 4.1 SignalEngine

| Member | Contract | Rationale |
|--------|----------|-----------|
| **generate(as_of_date, universe, data_context)** | **In:** `as_of_date: pd.Timestamp`, `universe: list[str]`, `data_context: DataContext`. **Out:** `tuple[dict[str, float], dict[str, Any]]` (scores, aux). | One entry point; backend chosen by `data_context` (e.g. `source == "precomputed"` → weekly path). |
| **Aux shape (typical)** | `atr_norms`, `regime_state`, `news_weight_used`, optional `buzz_by_ticker`, etc. | Caller passes aux into PolicyEngine; PolicyEngine may use or ignore. |

**Data flow:** DataContext → SignalEngine → (scores, aux). No Intent here; scoring only.

### 4.2 PolicyEngine

| Member | Contract | Rationale |
|--------|----------|-----------|
| **apply(as_of_date, scores, aux, context)** | **In:** `as_of_date`, `scores: dict[str, float]`, `aux: dict`, `context: Context`. **Out:** `tuple[dict[str, float], dict[str, Any]]` (gated_scores, flags). | Regime and kill-switch live in Context; policy is stateless. Same logic for backtest and execution (canonical _apply_backtest). |
| **Flags shape (typical)** | `cash_out: bool`, `action: str`, `regime`, `sideways_scale_applied`. | Used by pipeline and backtest for logging and exposure caps. |

**Data flow:** (scores, aux) + Context → PolicyEngine → (gated_scores, flags).

### 4.3 PortfolioEngine

| Member | Contract | Rationale |
|--------|----------|-----------|
| **build(as_of_date, gated_scores, context)** | **In:** `as_of_date`, `gated_scores: dict[str, float]`, `context: Context`. **Out:** `Intent`. | Ranking and top-N from context; sizing (e.g. inverse-vol or ATR) uses context/prices; output is always Intent. |

**Data flow:** (gated_scores, context) → PortfolioEngine → Intent.

### 4.4 Target weight pipeline (orchestration)

| Contract | Rationale |
|----------|-----------|
| **compute_target_weights(...)** builds DataContext and Context, calls SignalEngine → PolicyEngine → PortfolioEngine, optionally applies ML blend (apply_ml_blend) on scores before policy, returns weights (or weights + aux). | Single place that wires the spine and optional ML; scripts call this, not the three engines directly. |
| **Intent mode** | Derived from `path` (e.g. "weekly" → execution; else backtest). Injected into Intent.metadata or used to set Intent.mode. |

**Data flow:** (as_of, tickers, prices_dict, config, …) → compute_target_weights → (weights_series or (weights_series, aux)); internally: scores → [ML blend] → gated_scores → Intent → weights extracted.

---

## 5. Data Layer Interfaces

### 5.1 BaseDataProvider (`src/data/base_provider.py`)

| Method | Contract | Rationale |
|--------|----------|-----------|
| **get_historical_data(ticker, start_date, end_date?, **kwargs)** | Returns `pd.Series` (or DataFrame) of prices, datetime index. | Abstraction over CSV, IB, or other backends. |
| **get_current_price(ticker)** | Returns `float`. | For execution-time pricing (e.g. last close). |
| **get_name()** | Returns `str`. | Logging and diagnostics. |
| **is_available()** | Returns `bool`. Optional. | Health check before execution. |

**Data flow:** Scripts or pipeline obtain a provider via DataProviderFactory; they pass resulting prices (e.g. as `prices_dict`) into DataContext.

### 5.2 NewsDataSource (`src/data/news_base.py`) vs NewsProvider (`src/data/news_sources/base_provider.py`)

| Interface | Role | Rationale |
|-----------|------|-----------|
| **NewsDataSource** | Fetch + cache; `fetch_articles_for_ticker(ticker, start_date, end_date, use_cache)`. Used by pipeline/news_engine. | Caching and API quota live here; spine sees only preloaded news or paths. |
| **NewsProvider** | Provider-agnostic: `fetch_history`, `fetch_live`, `standardize_data`. Used by Tiingo/Marketaux etc. | Separates “raw fetch + standardize” from “cache and directory layout”. |

**Data flow:** News fetcher factory → NewsDataSource (or provider) → articles/DataFrames → news_dir or in-memory news_signals → DataContext.

### 5.3 DataProviderFactory / NewsFetcherFactory

| Contract | Rationale |
|----------|-----------|
| **create(type, **kwargs)** → BaseDataProvider or NewsDataSource. | Only place that knows concrete classes; callers depend on abstract interfaces. |
| **from_config_file(path?)** → instance. | Configuration-driven creation for scripts. |

---

## 6. Execution and Portfolio Interfaces

### 6.1 BaseExecutor (`src/execution/base_executor.py`)

| Method | Contract | Rationale |
|--------|----------|-----------|
| **submit_order(ticker, quantity, side, order_type, limit_price?, **kwargs)** | Returns `Dict` (order info). | Same surface for mock and IB. |
| **cancel_order(order_id)** | Returns `bool`. | Required for risk/circuit-breaker. |
| **get_positions()** | Returns `pd.DataFrame` (e.g. symbol, quantity, avg_cost, market_value). | PositionManager can adapt this to account_info shape. |
| **get_account_value()** | Returns `float` (NAV). | Sizing and risk. |
| **get_name()** | Returns `str`. | Logging. |

**Data flow:** ExecutorFactory → BaseExecutor. PositionManager takes an account_provider (executor or IBDataProvider) and uses get_positions + get_account_value (or get_account_info) to compute current weights and delta trades.

### 6.2 PositionManager

| Method | Contract | Rationale |
|--------|----------|-----------|
| **get_account_info()** | Returns dict with `margin_info`, `positions` (or pos_list). | Unifies IB and executor-backed flows. |
| **get_current_positions()** | Returns DataFrame: symbol, quantity, avg_cost, market_value, weight. | Standard shape for delta calculation. |
| **get_account_value()** | Returns float. | NAV. |
| **calculate_delta_trades(current_weights, optimal_weights, account_value, prices?)** | Returns trade list (buy/sell per ticker). | Converts Intent (as optimal_weights) + current state → executable deltas. |

**Data flow:** Intent (weights) → optimal_weights Series; current state from account_provider → current_weights; then calculate_delta_trades → orders → BaseExecutor.submit_order.

### 6.3 Fill ledger

| Contract | Rationale |
|----------|-----------|
| **append_fill_record(...)** writes one JSON-Lines record; **read_fill_ledger(path?)** returns list of records. | Append-only audit trail; path configurable for tests. |

---

## 7. Model Interfaces

### 7.1 BaseReturnPredictor (`src/models/base_predictor.py`)

| Method | Contract | Rationale |
|--------|----------|-----------|
| **fit(X, y, X_val?, y_val?)** | Trains model; returns metrics dict. | Same training interface for all model types. |
| **predict(X)** | Returns `np.ndarray` of predicted returns. | Inference used by apply_ml_blend. |
| **get_feature_importance()** | Returns `Dict[str, float]`. | Diagnostics and compliance. |
| **save_model(path)** / **load_model(path)** (class method) | Persist and restore. | Pipeline and run_execution load one model per process. |

**Data flow:** model_factory.create(config, feature_names) → BaseReturnPredictor. Training pipeline produces saved artifact; target_weight_pipeline (apply_ml_blend) loads and uses it to blend with base scores.

### 7.2 Model factory

| Contract | Rationale |
|----------|-----------|
| **create_model(model_config, feature_names)** → BaseReturnPredictor. **list_available_models()** → list of type names. | Only place that maps config type to concrete class; rest of code uses BaseReturnPredictor. |

---

## 8. End-to-End Data Flow (Summary)

```
1. Script loads config and data (prices, news, universe).
2. Script builds DataContext and Context (and optionally precomputed_indicators).
3. compute_target_weights(as_of, tickers, prices_dict, ...):
   a. SignalEngine.generate(as_of, universe, data_context) → (scores, aux).
   b. Optional: apply_ml_blend(scores, ...) → blended scores.
   c. PolicyEngine.apply(as_of, scores_or_blended, aux, context) → (gated_scores, flags).
   d. PortfolioEngine.build(as_of, gated_scores, context) → Intent.
   e. Return Intent.weights as Series (and optionally aux).
4. Backtest: use Intent (or weights) to update positions and compute returns.
5. Execution: Intent → optimal_weights_series; PositionManager.calculate_delta_trades(current, optimal, nav, prices) → orders → Executor.submit_order; append_fill_record for each fill.
```

---

## 9. Rationale Summary

| Choice | Rationale |
|--------|-----------|
| **DataContext / Context as dicts** | Caller-owned shape; spine stays agnostic to data source and config layout; easy to add keys without changing engine signatures. |
| **Intent as single execution output** | One contract for both backtest and live; no divergence in how target weights are interpreted. |
| **Policy always uses _apply_backtest** | Identical risk behavior in backtest and execution; no “weekly passthrough” that could hide regime risk. |
| **Factories for providers, executors, models** | Testability and swapping (mock vs IB, CSV vs IB, ridge vs xgboost) without touching spine or scripts. |
| **PositionManager accepts account_provider** | Same logic for “IB data provider” and “executor”; adapter pattern in get_account_info. |
| **Fill ledger append-only** | Audit and reconciliation; no in-memory only state for fills. |

This document defines structure, contracts, and rationale only. Implementation lives in the referenced modules; this is the single reference for interface and data-flow design.
