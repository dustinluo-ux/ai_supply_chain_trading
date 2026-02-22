# PROJECT OVERVIEW — AI Supply Chain Trading System
**Last Updated:** 2026-02-22 (end of day)
**Note:** This supersedes PROJECT_STATUS.md (last updated 2026-02-15, now stale).

---

## What This System Does

Quantitative trading system for AI/semiconductor supply chain stocks.
- **Universe:** 46 tickers across 4 pillars (Compute, Energy, Infrastructure, Adoption) + 5 global + SPY benchmark
- **Signal stack:** Technical Master Score + FinBERT news sentiment + Ridge ML model + Volatility-Adjusted Alpha Tilt optimizer + SPY Regime Gate
- **Execution:** Weekly rebalance via IBKR paper account DUM879076 (live NAV fetch confirmed); Monday auto-rebalance; Tue-Fri emergency brake monitoring
- **Data root:** `C:\ai_supply_chain_trading\trading_data\` (env var DATA_DIR)

---

## Directory Structure

```
ai_supply_chain_trading/
│
├── config/
│   ├── universe.yaml               # CANONICAL 46-ticker source (4 pillars + 5 global; NEP removed)
│   ├── data_config.yaml            # Watchlist + paths (synced FROM universe.yaml)
│   ├── model_config.yaml           # Feature names, active model path
│   ├── strategy_params.yaml        # Propagation weights, LLM triggers
│   ├── technical_master_score.yaml # Trend 40% / Momentum 30% / Volume 20% / Vol 10%
│   ├── config.yaml                 # news.enabled, news.data_dir, llm.enabled
│   └── trading_config.yaml
│
├── scripts/
│   ├── daily_workflow.py           # MAIN DAILY RUNNER (8 steps — see pipeline below)
│   ├── generate_daily_weights.py   # Signal table + appends to outputs/daily_signals.csv
│   ├── portfolio_optimizer.py      # Volatility-Adjusted Alpha Tilt + SPY regime gate
│   ├── regime_monitor.py           # VIX / SPY 200-SMA / SMH -5% → regime_status.json
│   ├── update_price_data.py
│   ├── update_news_data.py         # Marketaux primary + Tiingo secondary
│   ├── backtest_technical_library.py  # CANONICAL BACKTEST ENTRY POINT
│   ├── run_execution.py            # Execution spine + fill ledger
│   ├── reconcile_fills.py          # fills.jsonl vs target weights reconciliation
│   ├── sync_fills_from_ibkr.py     # Tuesday: pull Monday's fills from TWS
│   ├── update_signal_db.py         # Daily DB upsert + forward return computation
│   ├── generate_performance_report.py  # On-demand performance report (--weeks N)
│   ├── statistical_validation.py   # Bootstrap Sharpe CI + alpha t-test (3yr backtest)
│   ├── risk_report.py              # Drawdown, vol, beta, VaR, concentration
│   ├── train_ml_model.py           # Ridge model training + IC gate
│   ├── fetch_missing_prices.py     # EODHD OHLCV backfill
│   ├── ingest_eodhd_news.py        # EODHD news → parquet
│   ├── check_data_integrity.py     # 46-ticker data coverage diagnostic
│   ├── sync_universe.py            # universe.yaml → data_config.yaml
│   └── research_grid_search.py     # Parameter sweep
│
├── src/
│   ├── core/
│   │   ├── target_weight_pipeline.py  # CANONICAL SPINE (prices → signals → weights)
│   │   └── config.py                  # ENV config: DATA_DIR, NEWS_DIR, API keys
│   ├── signals/
│   │   ├── signal_engine.py           # Orchestrator (technical + news + LLM)
│   │   ├── technical_library.py       # Master Score
│   │   ├── news_engine.py             # FinBERT sentiment + lru_cache
│   │   ├── llm_bridge.py              # Gemini 2.0 Flash
│   │   ├── sentiment_propagator.py    # Supply chain sentiment cascade
│   │   └── feature_engineering.py    # sentiment_velocity, news_spike
│   ├── models/
│   │   ├── train_pipeline.py          # 7-feature extraction + Ridge training
│   │   ├── linear_model.py
│   │   └── model_factory.py
│   ├── data/
│   │   ├── csv_provider.py            # Price CSV loader
│   │   ├── news_fetcher_factory.py    # Lazy factory (marketaux, tiingo, etc.)
│   │   ├── news_base.py               # Cache + tz-aware logic
│   │   └── news_sources/
│   │       ├── base_provider.py       # ABC: NewsProvider
│   │       ├── marketaux_source.py    # LIVE operational news source
│   │       └── tiingo_provider.py     # 2025+ inference only
│   ├── execution/
│   │   ├── ibkr_bridge.py             # IBKR live (guards: min/max size, no shorts)
│   │   ├── ib_executor.py             # IBExecutor: TSE/SEHK/IBIS routing
│   │   ├── ibkr_nav.py                # fetch_nav() → live NAV from TWS (SGD base)
│   │   ├── mock_executor.py           # Dry-run (last-close price injection)
│   │   └── fill_ledger.py             # Append-only fills.jsonl
│   ├── portfolio/
│   │   └── position_manager.py        # Delta trade calculation
│   ├── evaluation/
│   │   └── performance_tracker.py
│   └── utils/
│       ├── storage_handler.py         # S3-ready StorageGateway (fastparquet)
│       ├── data_manager.py            # get_path(key) → canonical paths
│       └── config_manager.py
│
├── models/saved/
│   ├── ridge_20260221_230133.pkl  # ACTIVE — 7 features, alpha=0.001
│   ├── ridge_20260221_131840.pkl  # STALE — 5 features, do not load
│   └── ridge_20260221_123540.pkl  # STALE — 5 features, do not load
│
├── outputs/
│   ├── daily_signals.csv          # Appended daily by generate_daily_weights.py
│   ├── last_signal.json           # Latest snapshot (source for health table)
│   ├── last_valid_weights.json    # Optimizer output (target weights, as_of)
│   ├── last_optimized_weights.json  # Optimizer output with metadata + regime
│   ├── portfolio_state.json       # Source of truth: NAV, holdings (% only), weekly lock
│   ├── regime_status.json         # Latest regime: VIX, SPY 200-SMA, SMH, score_floor
│   ├── trading.db                 # SQLite: signals, forward_returns, portfolio_daily
│   ├── fills/fills.jsonl          # Execution fill ledger (append-only)
│   └── backtest_2022/2023/2024.json
│
├── docs/
│   ├── ARCHITECTURE.md            # IMMUTABLE — requires Proposal Review to edit
│   ├── STRATEGY_MATH.md           # IMMUTABLE — requires Proposal Review to edit
│   ├── DECISIONS.md               # Authoritative architectural decision log
│   ├── RESEARCH_ARCHIVE.md        # ML architecture decisions + rejected strategies
│   ├── INDEX.md                   # System reference
│   ├── PROJECT_OVERVIEW.md        # THIS FILE
│   └── research/
│       ├── portfolio_construction.md  # Method comparison + D022 (alpha tilt selection)
│       └── regime_management.md       # D023: SPY gate (entry hurdle + emergency exit)
│
└── .tasks/
    └── sunday_start.md            # Active task queue
```

---

## Signal Stack (How Weights Are Computed)

```
Price CSVs + News JSON
        ↓
Technical Master Score     (Trend 40%, Momentum 30%, Volume 20%, Vol 10%)
        +
News Engine (FinBERT)      (sentiment score per ticker, lru_cache)
        +
Sentiment Propagator       (supply chain cascade from hub tickers)
        +
Ridge ML Model (7 features) → Z-scored ML score
        ↓
Blend: Final = 0.7 × Baseline + 0.3 × ML_Score
        +
Gemini LLM Gate            (optional, config-gated)
        +
Vol Filter                 (top 5% 20-day vol → flag/reduce)
        ↓
regime_monitor.py          (SPY 200-SMA → BULL score_floor=0.50 / BEAR score_floor=0.65)
        ↓
Volatility-Adjusted Alpha Tilt  (weight = score/vol, top-quartile eligible, 25% cap)
        ↓
portfolio_state.json       (target_weights %, holdings, weekly lock, last_nav from IBKR)
        ↓
IBKR Paper Execution       (Monday only; Tue-Fri: VIX>30 / SPY<200SMA / SMH-5% → liquidate)
```

**Active ML model:** `models/saved/ridge_20260221_230133.pkl`
- Features: `momentum_avg`, `volume_ratio_norm`, `rsi_norm`, `news_supply`, `news_sentiment`, `sentiment_velocity`, `news_spike`
- Walk-forward IC gate: mean IC = 0.0202 (4 folds) — PASSED threshold of 0.02

---

## Data Sources

| Source | What | When |
|--------|------|------|
| Local CSVs (FNSPID/Polygon) | Historical OHLCV | Training (2020–2024) |
| EODHD | OHLCV for global tickers + news backfill | Training supplement |
| Marketaux | News articles (live) | Operational / daily |
| Tiingo | News articles | 2025+ live inference only |
| SPY CSV | Benchmark for regime detection | Always required |

**News policy:** Pre-2025 training rows use `news_supply=0.5`, `news_sentiment=0.5` (neutral). No usable historical news backfill exists (Tiingo API does not honor date params).

---

## Task / Phase Status

### Scaling Ritual (completed 2026-02-21)

| Task | Description | Status |
|------|-------------|--------|
| Task 1 | Architecture B dead code purge | DONE |
| Task 2 | Provider-agnostic data layer (base_provider ABC) | DONE |
| Task 3a | Tiingo integration (TiingoProvider, backfill script) | DONE |
| Task 4 | Universal data abstraction (StorageGateway, data_manager, S3-ready) | DONE |
| Task 6 | 40-ticker universe hard-reset + weight finalization | DONE |
| Task 7 | Automated dry run + performance tracking (daily_workflow.py) | DONE |
| Task 8 | Visual health check (rich System Health table) | DONE |
| Task 9 | Universe sync (sync_universe.py → universe.yaml canonical) | DONE |

### Phase 3: ML Integration (completed 2026-02-21)

| Item | Status |
|------|--------|
| Feature engineering (sentiment_velocity, news_spike) | DONE |
| Ridge alpha=0.001, 7 features, trained on 47 tickers (4319 samples) | DONE |
| Walk-forward IC gate (mean IC = 0.0202) | PASSED |
| ML wired into target_weight_pipeline (0.7 + 0.3 blend) | DONE |
| Sanity check: ML bearish + baseline bullish → 0.5× position | DONE |
| AAPL/MSFT intent contamination fix | DONE |

### Phase 4: Risk Management + Live Plumbing (completed 2026-02-22)

| Item | Status | Notes |
|------|--------|-------|
| Statistical validation (bootstrap Sharpe CI, alpha t-test) | DONE | CI [1.163, 3.013]; alpha p=0.053; hit rate 55.4% |
| BEAR regime hard gate (score_floor → 0.65 under SPY < 200-SMA) | DONE | portfolio_optimizer.py |
| regime_monitor.py (VIX / SPY 200-SMA / SMH → regime_status.json) | DONE | Single source of truth for score_floor |
| Dynamic score_floor (BULL=0.50 / BEAR=0.65 from regime_monitor) | DONE | Optimizer reads regime_status.json first |
| Intraweek regime monitor + emergency brake | DONE | daily_workflow.py Tue-Fri liquidation path |
| portfolio_state.json (% only, no dollar amounts) | DONE | target_weights, holdings, weekly lock |
| IBKR NAV live fetch (SGD account DUM879076) | DONE | ibkr_nav.fetch_nav() → 1,004,194 SGD confirmed |
| Volatility-Adjusted Alpha Tilt optimizer | DONE | weight=score/vol; top-quartile; 25% cap |
| docs/research/ (portfolio_construction.md, regime_management.md) | DONE | D022 + D023 recorded |
| RESEARCH_ARCHIVE.md | DONE | ML decisions, rejected strategies |
| NEP removed from universe (delisted) | DONE | 47 → 46 tickers |

### Backtest Results (validated)

| Year | Sharpe | Return | Max Drawdown | Notes |
|------|--------|--------|--------------|-------|
| 2022 | -0.2759 | -17.95% | -20.65% | Broad tech bear; SPY -19% |
| 2023 | +0.3399 | +78.10% | -19.93% | NVDA/AMD news active |
| 2024 | +0.1985 | +33.88% | -10.31% | vs S&P ~25%, NASDAQ ~29% |

**Statistical validation (3-year combined, 2026-02-22):**
- Bootstrap Sharpe 95% CI: [1.163, 3.013] — entirely above zero
- Alpha t-test vs SPY: mean +0.82%/week (+42.6% ann.), p=0.053
- Hit rate vs SPY: 55.4% (87/157 weeks)
- Max drawdown percentile: 57th (normal range)

---

## Current Open Items (as of 2026-02-22)

| Item | Priority | Notes |
|------|----------|-------|
| Data gaps (NVDA, AMD, TSM, ASML + 10 others) | Medium | Gaps >5 cal days — likely corporate actions, not errors |
| IBKR fill reconciliation | Medium | fills.jsonl exists; reconcile_fills.py + sync_fills_from_ibkr.py written but not tested end-to-end |
| Scheduling automation | Medium | Manual runs only; no cron/APScheduler wired |
| Real-time data feeds | Low/Future | Historical CSVs only |
| ~~Statistical validation~~ | ~~Low~~ | DONE 2026-02-22 — see Backtest Results above |

---

## Road to Live Trading

| Layer | Readiness | Blocker |
|-------|-----------|---------|
| Research / Backtest | 100% — DONE | — |
| ML Model | 100% — DONE | — |
| Data Infrastructure | 100% — DONE | — |
| Statistical Validation | 100% — DONE | — |
| Daily Operations | 100% — DONE | — |
| Monitoring Dashboard | 100% — DONE | — |
| Risk Management (regime gate, emergency brake) | 100% — DONE | — |
| Paper Trading | ~80% | Fill reconciliation loop + scheduling not automated |
| Live Trading | ~25% | Real-time feeds, fill reconciliation, scheduling missing |

---

## Key Commands

```bash
# Daily (run every morning)
python scripts/daily_workflow.py

# Backtest (research)
python scripts/backtest_technical_library.py --start 2023-01-01 --end 2023-12-31 --no-llm

# Statistical validation (3-year bootstrap + alpha t-test)
python scripts/statistical_validation.py --no-llm

# Regime status (refresh regime_status.json)
python scripts/regime_monitor.py

# On-demand performance report
python scripts/generate_performance_report.py --weeks 4

# Retrain ML model
python scripts/train_ml_model.py

# Check data coverage
python scripts/check_data_integrity.py

# Sync universe (after editing universe.yaml)
python scripts/sync_universe.py

# Dry-run execution
python scripts/run_execution.py --dry-run
```

---

## Governance

- `docs/ARCHITECTURE.md` and `docs/STRATEGY_MATH.md` are **immutable** — require Proposal Review before any edits
- `docs/DECISIONS.md` is the authoritative "why" record for all architectural choices
- Interface changes require explicit user approval per `AI_RULES.md`
- Canonical news path: `C:\ai_supply_chain_trading\trading_data\news\` (from `.env` NEWS_DIR)
