# ARCHITECTURE — System Design & Data Flow

**Last Updated:** 2026-02-14

Single source of truth for system architecture, data flow, and key paths. Technical indicator math lives in `TECHNICAL_SPEC.md`. Backtest execution details live in `BACKTEST_JOURNAL.md`.

---

## Design Principles

1. **Multi-source data strategy:** Support seamless alternation between legacy (FNSPID + Polygon) and new (Tiingo + yfinance + Marketaux) via configuration.
2. **wealth_signal_mvp_v1:** Read-only reference for code porting. All active implementation in **ai_supply_chain_trading**.
3. **Expansion-only architecture:** Expand capabilities without removing existing modules.
4. **Overlay strategy:** Regime (3-state HMM) and News Alpha (Buzz, Surprise, Sector, Event) are multipliers/filters on top of base Master Score. No deletion of existing technical logic.

---

## Four System Pillars

| Pillar | Summary |
|--------|---------|
| **1. Data & Environment** | API keys in .env (TIINGO, MARKETAUX, GOOGLE_API). Warm-up: last 30 days to bridge historical ↔ real-time. Self-healing: every live fetch appends to historical store. |
| **2. Market Data (IBKR)** | IBKR TWS via ib_insync. Volume: reqMktData Tick 8 with ×100 for US equities. Client ID rotation @ 99; yfinance cache initialization. |
| **3. Sentiment & Inference** | Dual-stream news: Marketaux + Tiingo. Gemini → strict JSON `{ticker, score, relevance, impact}`; sentiment -1 to 1; live matches FNSPID scale. |
| **4. Operational Cadence** | Weekly rebalance: Composite Score (Master Score / Price Momentum + Weighted Sentiment) → rank → BUY/SELL/HOLD. |

---

## Core Architecture: Single Spine Design

### Three Core Engines (Canonical Contract)

1. **SignalEngine** (`src/core/signal_engine.py`)
   - Produces technical signals and master scores
   - Backtest mode: uses `technical_library` + optional `news_engine`
   - Weekly mode: uses precomputed outputs from `SignalCombiner`
   - Same interface, different backends

2. **PolicyEngine** (`src/core/policy_engine.py`)
   - Applies regime detection and policy gates
   - Backtest mode: full gates (CASH_OUT, sideways scaling, daily exit)
   - Weekly mode: passthrough (no regime or gates applied)

3. **PortfolioEngine** (`src/core/portfolio_engine.py`)
   - Constructs portfolio intent (ranking, top-N selection, position sizing)
   - Execution via `src/portfolio/position_manager`

### Module Organization

```
src/
├── core/               # Single spine engines
│   ├── signal_engine.py
│   ├── policy_engine.py
│   ├── portfolio_engine.py
│   ├── intent.py
│   └── types.py
├── signals/            # Signal generation
│   ├── technical_library.py      # Master Score computation
│   ├── news_engine.py             # News Alpha strategies
│   ├── signal_combiner.py         # Legacy combined signals
│   ├── weight_model.py            # Dynamic weighting
│   ├── regime.py                  # Regime detection
│   └── performance_logger.py      # Metrics & memory
├── portfolio/          # Position management
│   ├── sizing.py
│   └── position_manager.py
├── execution/          # Order execution
│   ├── executors.py   # Mock / IB
│   └── factory.py
├── data/              # Data providers (opaque boundary)
│   ├── price_fetcher.py
│   ├── news_fetcher.py
│   └── ib_provider.py
└── utils/             # Logging, guards, helpers
    ├── logger.py
    ├── defensive.py
    └── ticker_utils.py
```

---

## Data Flow (End-to-End)

### 1. Configuration → Data Directories

- **Config file:** `config/data_config.yaml`
- **Key parameter:** `data_sources.data_dir` (e.g. `data/stock_market_data` or absolute path)
- **Default:** `{PROJECT_ROOT}/data/stock_market_data`
- **Code reference:** `scripts/backtest_technical_library.py` → `load_config()` reads `data_sources.data_dir`

### 2. Price Data Ingestion (CSV Format)

**Directory structure:**
```
{data_dir}/
├── nasdaq/csv/
├── sp500/csv/
├── nyse/csv/
└── forbes2000/csv/
```

**Lookup logic:**
- `find_csv_path(data_dir, ticker)` → searches subdirectories for `{TICKER}.csv`
- First match wins

**Loading:**
- `load_prices(data_dir, tickers)` → `pd.read_csv`
- Index: column 0, parsed as dates
- Columns: lowercased, required `close`; optional `open/high/low/volume` default from `close` if missing
- Output: `prices_dict[ticker]` = DataFrame with OHLCV, tz-naive datetime index

### 3. Signal Generation (Master Score)

**Input preparation:**
- Per-ticker slice: `df[df.index <= monday]` (strict no-look-ahead)

**Processing:**
- Module: `src.signals.technical_library`
- Functions:
  - `calculate_all_indicators(slice_df)` → raw + normalized indicators
  - `compute_signal_strength(row)` → Master Score

**Configuration:**
- File: `config/technical_master_score.yaml`
- Contents: category weights, rolling windows, indicator→category mapping

**Output:**
- Master Score per ticker (0-1 scale)
- ATR_norm from **Signal Day − 1** for inverse-volatility sizing

### 4. News Alpha Overlay → Master Score

**Pipeline:**
```
Raw JSON                    NewsEngine              NewsComposite         MasterScore
(data/news/{ticker}_news.json) → (FinBERT + spacy) → (Strategies A-D) → (Technical + News)
```

**Module:** `src.signals.news_engine`

**Key function:**
```python
compute_news_composite(news_dir, ticker, as_of, ...) 
→ news_composite ∈ [0, 1]
```

**Strategies:**
- **A (Buzz):** Z-score of article volume
- **B (Surprise):** Sentiment delta vs baseline
- **C (Sector Relative):** Cross-sectional ranking
- **D (Event-Driven):** Catalyst detection via spacy EventDetector

**Deduplication:**
- Levenshtein fuzzy matching on headlines (ratio > 0.85 = duplicate)
- Prevents double-counting from DualStream (Marketaux + Tiingo)

**Blending formula:**
```python
when news_weight > 0:
    final_master = (1 - news_weight) × technical_master + news_weight × news_composite
```
Default: `news_weight = 0.20` (80% technical, 20% news)

**Model selection:**
- **FinBERT:** Bulk backtesting (fast, local)
- **Gemini:** Deep dives on top tickers only

### 5. Dynamic Weighting & 3-State Regime (Overlay)

**Execution point:** Between signal generation and portfolio sizing

**Modes (via `--weight-mode`):**

| Mode | Engine | Description |
|------|--------|-------------|
| `fixed` | Config | Static category weights from YAML |
| `regime` | hmmlearn | 3-State HMM (BULL/BEAR/SIDEWAYS) → adaptive weights |
| `rolling` | PyPortfolioOpt | EfficientFrontier (max_sharpe) or HRPOpt |
| `ml` | Scikit-Learn | Random Forest + TimeSeriesSplit CV |

**3-State Regime Logic (hmmlearn):**
```python
get_regime_hmm(..., n_components=3) → BULL / BEAR / SIDEWAYS
```

**State mapping:**
- **BULL** (highest mean return, low volatility) → BULL_WEIGHTS
- **BEAR** (lowest mean return, high volatility) → DEFENSIVE_WEIGHTS
  - **CASH_OUT trigger:** BEAR + SPY < 200-SMA (dual confirmation)
- **SIDEWAYS** (mean ≈ 0, moderate volatility) → SIDEWAYS_WEIGHTS
  - Position size × 0.5

**Fallback:** SPY vs 200-SMA binary rule if HMM fails

**Safety constraint:**
- All weight inputs use only T−1 or earlier data (no look-ahead)

### 6. Portfolio Construction & Backtesting

**Rebalance frequency:** Weekly (Mondays)

**Entry timing:** Next-Day Open (no look-ahead)

**Position sizing:** Inverse-volatility weights

**Regime overlay:**
- BEAR + SPY < 200-SMA → CASH_OUT (100% cash)
- SIDEWAYS → position × 0.5

**Return calculation:**
- First day of block: `(close − open) / open`
- Subsequent days: close-to-close percent change

**Transaction costs:** 0.15% (15 bps) per trade

**Risk management:**
- Daily risk exit: e.g. ≤ −5% → exit without reallocating to other positions

**Logging (when `--weight-mode regime`):**
```
[STATE] {Date} | Regime: B/E/S | News Buzz: T/F/- | Action: Trade/Cash
[REGIME] Date, HMM State, Mean Return, Volatility
```

**Backtest function:**
```python
run_backtest_master_score(prices_dict, data_dir, ...) 
→ positions_df, returns, portfolio_returns, Sharpe, total_return, max_drawdown
```

### 7. Execution (Live / Paper)

**Entry point:** `run_weekly_rebalance.py` (dry-run or live)

**Pipeline:**
1. Composite score calculation
2. Ranking
3. BUY/SELL/HOLD decision generation

**IBKR integration:**
- Code location: `src/execution/`
- Status: Exists but not wired in default path
- Reference: SYSTEM_SPEC in archive if needed

---

## Data Source Paths (Legacy vs New)

### Legacy Path
- **FNSPID:** `data/raw/`, `data/news/`
- **Polygon** → Marketaux-compatible JSON
- Same downstream signal/backtest processing

### New Path
- **Sources:** Tiingo + yfinance + Marketaux
- **Warm-up:** Merges last 30 days with historical data
- **Self-healing:** Appends to `data/prices/` (or configured directory)

### Configuration Toggle
- Unified schema into signals and backtest
- Config/data-source selector for seamless alternation

---

## Key File Paths Reference

| Purpose | Path |
|---------|------|
| **Price data (backtest)** | `config/data_config.yaml` → `data_sources.data_dir` → `{data_dir}/{nasdaq,sp500,nyse,forbes2000}/csv/{TICKER}.csv` |
| **Price data (parquet)** | `data/prices/` (warm-up/self-healing target) |
| **News data** | `data/news/` (JSON per ticker)<br>`data/raw/` (FNSPID CSV) |
| **Configuration** | `config/data_config.yaml`<br>`config/technical_master_score.yaml`<br>`config/signal_weights.yaml`<br>`config/trading_config.yaml` |
| **Logs** | `logs/` (via `src.utils.logger.setup_logger()`)<br>`outputs/backtest_master_score_*.txt` |
| **SPY benchmark** | `data/stock_market_data/sp500/csv/SPY.csv` |

---

## Warm-Up and Self-Healing (When Active)

**Module:** `src/data/warmup.py`

**Warm-up process:**
1. Load historical from `data/prices/`
2. Optional: fetch last 30 days from yfinance
3. Merge with no gaps

**Self-healing process:**
1. After live fetch: `heal_append(ticker, new_bars_df, data_dir)`
2. Append new bars to existing data
3. Drop duplicate dates

---

## Canonical Entry Points

**Research/Backtest:**
- `scripts/backtest_technical_library.py` (authoritative)
- `scripts/research_grid_search.py`

**Non-canonical (experimental/legacy):**
- `run_phase1_test.py`
- `run_phase2_pipeline.py`
- `run_phase3_backtest.py`
- `run_strategy.py`
- `run_technical_backtest.py`
- `simple_backtest_v2.py`
- `test_signals.py`

These scripts may run but are not part of the canonical workflow.

---

## Dependencies & External Engines

**Core libraries:**
- `pandas_ta` — all technical indicator math
- `PyYAML` — configuration parsing

**Dynamic weighting & regime:**
- **PyPortfolioOpt** — EfficientFrontier (max_sharpe) or HRPOpt for category weights
- **hmmlearn** — Gaussian HMM (3 states) for BULL/BEAR/SIDEWAYS regime detection
- **Scikit-Learn** — Random Forest Regressor + TimeSeriesSplit CV for ML mode

**News Alpha:**
- **transformers + ProsusAI/finbert** — sentiment analysis on headlines/bodies
- **spacy (en_core_web_md)** — EventDetector (NER + phrase matching)
  - Run: `python -m spacy download en_core_web_md`
- **Levenshtein** — headline fuzzy matching for deduplication

**Execution:**
- **ib_insync** — IBKR TWS integration

**Note:** No custom optimization or ML math from scratch. Normalization uses static formulas for bounded indicators, rolling min-max for unbounded (no sklearn for normalization).
