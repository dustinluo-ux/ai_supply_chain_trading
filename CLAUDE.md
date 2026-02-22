● Session Summary

  What we fixed (all committed & pushed through 2026-02-18, plus 2026-02-19 fixes below)

  ┌──────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────┐
  │                         Fix                          │                             File(s)                             │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Live price update wired into weekly rebalance        │ scripts/update_price_data.py, run_weekly_rebalance.py           │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Live news update (Marketaux) wired in                │ scripts/update_news_data.py (new), run_weekly_rebalance.py      │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ News pipeline gap: news_dir hardcoded None           │ src/core/target_weight_pipeline.py, config/config.yaml          │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ News loader format-agnostic (flat + monthly chunks)  │ src/signals/news_engine.py                                      │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ News cache tz-aware bug (burning API quota)          │ src/data/news_base.py                                           │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ src/data/ never tracked in git (gitignore bug)       │ .gitignore                                                      │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ news_fetcher_factory.py crashing on missing packages │ src/data/news_fetcher_factory.py                                │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Regime detection never ran (need_regime=False)       │ scripts/backtest_technical_library.py                           │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Weight assertion crash (propagated tickers, non-BEAR)│ scripts/backtest_technical_library.py                           │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Weight assertion crash (propagated tickers, BEAR)    │ scripts/backtest_technical_library.py                           │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Gemini load_dotenv() missing                         │ src/signals/llm_bridge.py                                       │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ --no-llm flag to skip Gemini in backtests            │ backtest_technical_library.py, signal_engine.py, news_engine.py │
  ├──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ End-to-end backtest validated (exit 0, 2022 full yr) │ —                                                               │
  └──────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘

  ---
  Backtest 2022 result (baseline, --no-llm, propagation on)

  Sharpe: -0.2759 | Total return: -17.95% | Max drawdown: -20.65%
  (2022 was a broad tech bear year; SPY fell ~19% — strategy roughly in line with benchmark)

  ---
  Nothing in flight. System is clean.

---
## Phase 3 Pivot (2026-02-21): Technical-First ML Model

### Decision
Tiingo news API does not provide historical article backfill — `startDate`/`endDate` params are
ignored and all returned articles carry ~2025-11-xx publication dates regardless of the requested
date range. Confirmed after two full re-backfills with cache bypassed (`use_cache=False`).

### News Data Policy
- **2025-present (live)**: Tiingo via `TiingoProvider` — real publication dates, valid signal
- **Pre-2025 (training)**: No usable historical news. `news_supply` and `news_sentiment` features
  default to **0.5** (neutral) for all 2022–2024 training rows
- Marketaux flat files (`{ticker}_news.json`) in `C:\ai_supply_chain_trading\trading_data\news\`
  remain the operational news source for the live weekly rebalance signal engine

### ML Training Feature Set (Technical-First)
Active features: `momentum_avg`, `volume_ratio_norm`, `rsi_norm`
News features (`news_supply`, `news_sentiment`): zeroed/neutral during 2022–2024 training;
live-scored via Tiingo for 2025+ inference only.

### Data Location
All trading data lives at: `C:\ai_supply_chain_trading\trading_data\`
- Price CSVs: `trading_data\stock_market_data\{nasdaq,sp500,nyse,forbes2000}\csv\`
- News JSON (Marketaux): `trading_data\news\{ticker}_news.json`
- Tiingo parquets: `trading_data\news\tiingo_{YYYY}_{MM}.parquet`
- Env var: `DATA_DIR=C:\ai_supply_chain_trading\trading_data` (set in `.env`)
