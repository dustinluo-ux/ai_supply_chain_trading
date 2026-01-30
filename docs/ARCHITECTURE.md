# Target Architecture — Multi-Source Quant Pipeline

**Last Updated:** 2026-01-29

Single source of truth for system architecture, data flow, and key paths. Technical indicator and backtest details live in `TECHNICAL_SPEC.md` and `BACKTEST_JOURNAL.md`.

---

## Principles

1. **Historical data:** Keep FNSPID and Polygon-based analysis. Expand with Tiingo, yfinance, Marketaux. Support **seamless alternation** between legacy (FNSPID + Polygon) and new (Tiingo + yfinance + Marketaux) via config.
2. **wealth_signal_mvp_v1:** Read-only; source of code to port. All implementation in **ai_supply_chain_trading**.
3. **ai_supply_chain_trading:** Expand only; no removal of existing modules.
4. **Overlay strategy:** Regime (3-state HMM) and News Alpha (Buzz, Surprise, Sector, Event) are **multipliers/filters on top of** the base Master Score. Do not delete existing technical logic; add Regime and News as overlays.

---

## Four Pillars

| Pillar | Summary |
|--------|--------|
| **1. Data & environment** | Keys in .env (TIINGO, MARKETAUX, GOOGLE_API). Warm-Up: last 30 days to bridge historical ↔ real-time. Self-healing: every live fetch appends to historical store. |
| **2. Execution & market data (IBKR)** | IBKR TWS via ib_insync. Volume: reqMktData Tick 8 with x100 for US equities. Client ID rotation @ 99; yfinance cache init. |
| **3. Sentiment & inference** | Dual-stream news: Marketaux + Tiingo. Gemini → strict JSON `{ticker, score, relevance, impact}`; sentiment -1 to 1; live matches FNSPID scale. |
| **4. Operational cadence** | Weekly rebalance: Composite Score (Master Score / Price Momentum + Weighted Sentiment) → rank → BUY/SELL/HOLD. |

---

## Data Flow (Verified Against Code)

End-to-end path from ingest to execution, as implemented.

### 1. Config → Data Dir

- **File:** `config/data_config.yaml`
- **Key:** `data_sources.data_dir` (e.g. `data/stock_market_data` or absolute path)
- **Code:** `scripts/backtest_technical_library.py` → `load_config()` reads `data_sources.data_dir`; default `ROOT / "data" / "stock_market_data"`

### 2. Price Ingest (CSV)

- **Paths:** Under `data_dir`, subdirs `nasdaq/csv`, `sp500/csv`, `nyse/csv`, `forbes2000/csv`
- **Lookup:** `find_csv_path(data_dir, ticker)` → first existing `{data_dir}/{sub}/{TICKER}.csv`
- **Load:** `load_prices(data_dir, tickers)` → `pd.read_csv`, index col 0, parse_dates; columns lowercased; required: `close`; optional `open`/`high`/`low`/`volume` defaulted from `close` if missing
- **Output:** `prices_dict[ticker]` = DataFrame with `open`, `high`, `low`, `close`, `volume`, tz-naive datetime index

### 3. Signals (Master Score)

- **Input:** Per-ticker slice `df[df.index <= monday]` (no future data)
- **Module:** `src.signals.technical_library` → `calculate_all_indicators(slice_df)`, `compute_signal_strength(row)`
- **Config:** `config/technical_master_score.yaml` (category weights, rolling window, indicator→category mapping)
- **Output:** Master Score per ticker; ATR_norm from **Signal Day − 1** for inverse-volatility sizing

### 3b. News Alpha → Master Score Overlay

- **Flow:** Raw JSON (`data/news/{ticker}_news.json`) → **NewsEngine** (FinBERT + spacy EventDetector) → **NewsComposite** (strategies A–D: Buzz, Surprise, Sector-relative, Event-driven) → **MasterScore**.
- **Module:** `src.signals.news_engine` — `compute_news_composite(news_dir, ticker, as_of, ...)` returns `news_composite` in [0, 1]. Deduplication via Levenshtein on headlines before processing.
- **Blend:** When `news_weight` &gt; 0 in config, `compute_signal_strength(row, news_composite=...)` produces `final_master = (1 - news_weight) * technical_master + news_weight * news_composite`.
- **FinBERT vs Gemini:** FinBERT used for bulk backtesting (fast, local); Gemini reserved for deep dives on top tickers.

### 3a. Weight Optimization & 3-State Regime (Overlay)

- **Step:** Between signal generation and portfolio sizing. Optional, driven by `--weight-mode` (fixed / regime / rolling / ml). **Overlay:** Regime and News are **multipliers/filters on top of** base Master Score; no removal of existing technical logic.
- **3-State Regime (hmmlearn):** `get_regime_hmm(..., n_components=3)` → BULL / BEAR / SIDEWAYS. **BULL** → BULL_WEIGHTS; **BEAR** → DEFENSIVE_WEIGHTS, and **CASH_OUT** if SPY &lt; 200-SMA; **SIDEWAYS** → SIDEWAYS_WEIGHTS, position size × 0.5. Fallback: SPY vs 200-SMA binary.
- **Rolling:** `get_optimized_weights(..., method="hrp"|"max_sharpe")` — PyPortfolioOpt; weight_bounds=(0.10, 0.50). When mode is rolling, HRPOpt can adjust category weights by regime performance.
- **ML:** `get_ml_weights(history)` — Random Forest + TimeSeriesSplit; fallback to fixed weights if CV R² &lt; 0.
- **Safety:** All weight inputs use only T−1 or earlier data.

### 4. Portfolio & Backtest

- **Positions:** Weekly rebalance (Mondays); entry at **Next-Day Open**; inverse-volatility weights; **3-State Regime overlay:** BEAR + SPY &lt; 200-SMA → CASH_OUT; SIDEWAYS → position × 0.5.
- **Returns:** First day of each block = (close − open) / open; rest = close-to-close; friction 0.15% per trade; daily risk exit (e.g. −5%) without reallocating exited weight.
- **Backtest logs:** When `--weight-mode regime`, prints `[STATE] {Date} | Regime: B/E/S | News Buzz: T/F/- | Action: Trade/Cash` and `[REGIME] Date, HMM State, Mean Return, Volatility`.
- **Code:** `run_backtest_master_score(prices_dict, data_dir, ...)` → positions_df, returns, portfolio_returns, Sharpe, total return, max drawdown.

### 5. Execution (Live / Paper)

- **Entry:** `run_weekly_rebalance.py` (dry-run or live); composite score → rank → BUY/SELL/HOLD
- **IB:** Code in `src/execution/` exists; not wired in default path (see SYSTEM_SPEC in archive if needed)

---

## Legacy vs New Paths

- **Legacy:** FNSPID (`data/raw/`, `data/news/`), Polygon → Marketaux-compatible JSON. Same downstream signal/backtest.
- **New:** Tiingo + yfinance + Marketaux; Warm-Up merges last 30d with historical; self-healing appends to `data/prices/` (or configured dir).
- **Alternation:** Config/data-source selector; unified schema into signals and backtest.

---

## Key Paths

| Purpose | Path |
|--------|------|
| Price (backtest) | `config/data_config.yaml` → `data_sources.data_dir` → `{data_dir}/{nasdaq,sp500,nyse,forbes2000}/csv/{TICKER}.csv` |
| Price (parquet) | `data/prices/` (warm-up/self-healing target when used) |
| News | `data/news/` (JSON per ticker), `data/raw/` (FNSPID CSV) |
| Config | `config/data_config.yaml`, `config/technical_master_score.yaml`, `config/signal_weights.yaml`, `config/trading_config.yaml` |
| Logs | `logs/` (`src.utils.logger.setup_logger()`); backtest logs `outputs/backtest_master_score_*.txt` |

---

## Warm-Up and Self-Healing (When Used)

- **Warm-Up:** `src/data/warmup.py` — historical from `data/prices/`, optional last 30d from yfinance, merged with no gap.
- **Self-Healing:** After live fetch, `heal_append(ticker, new_bars_df, data_dir)` appends new bars; duplicate dates dropped.
