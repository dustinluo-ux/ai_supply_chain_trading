# AI Supply Chain Quantitative Trading System

**An autonomous end-to-end quantitative trading pipeline: dynamic data ingestion → rolling ML model training → OOS backtest → portfolio construction → autonomous parameter optimization → scheduled re-runs.**

---

## Why it exists

Most retail algorithmic trading systems require constant manual intervention: re-running backtests, adjusting parameters, deciding when to rebalance. This system eliminates that. Once configured, it ingests fresh price and news data, retrains its own model on a rolling window, validates the strategy out-of-sample, sizes positions, and schedules its own next run — no human steps required between weekly cycles. The goal is a system that could run unattended for months while remaining auditable and overridable at any point.

---

## Quick Start

```bash
conda activate wealth

# Create .env from .env.example
# Required: GOOGLE_API_KEY (or GEMINI_API_KEY), MARKETAUX_API_KEY
# Optional: IBKR_PORT, DATA_DIR
```

### Run the full E2E pipeline (once)

```bash
python scripts/run_e2e_pipeline.py
```

### Paper trading (requires TWS running on port 7497)

```bash
# Dry-run: live prices + account data, no order submission
python scripts/run_execution.py --tickers NVDA,AMD,TSM,NQ --mode paper --ibkr-port 7497

# Submit real orders to paper account
python scripts/run_execution.py --tickers NVDA,AMD,TSM,NQ --mode paper --ibkr-port 7497 --confirm-paper

# Check fill status
python scripts/run_execution.py --tickers NVDA,AMD,TSM --mode paper --check-fills
```

Stages:
1. Price + news data refresh
2. Rolling ML model training (4-year window, auto-patched)
3. OOS backtest — writes `outputs/e2e_oos_backtest.json`
4. Mock execution — writes `outputs/last_valid_weights.json`
5. ASCII summary + STATUS: PASS/WARN/FAIL + exit code

### Smoke test (skip data, 2 trials)

```bash
python scripts/run_optimizer.py --n-trials 2 --skip-data
```

### Full autonomous optimizer run (30 trials, ~2-4 hrs)

```bash
python scripts/run_optimizer.py
```

After completion: winner params promoted to `config/strategy_params.yaml`, next weekly run scheduled via Windows Task Scheduler.

---

## Pipeline Architecture

```
run_optimizer.py
  └── N × run_e2e_pipeline.py --skip-model
        Stage 1: update_price_data + update_news_data
        Stage 2: run_factory  →  rolling 4yr window  →  factory_winner.json
        Stage 3: OOS backtest  →  e2e_oos_backtest.json
        Stage 4: run_execution (mock)  →  last_valid_weights.json
        Stage 5: summary print + exit code
  └── composite = 0.5×Sharpe + 0.3×CAGR + 0.2×(1 - |maxDD|)
  └── run_promoter.py  →  strategy_params.yaml  (atomic, .bak kept)
  └── schtasks  →  AITrading_WeeklyOptimizer  (next Mon 06:00)
```

---

## Key Configuration

`config/optimizer_config.yaml` is the **single file to review before any run**. It contains three sections:

| Section | Purpose |
|---------|---------|
| `optimizer` | n_trials, min_sharpe, run_interval_days, `composite_weights` (scoring formula) |
| `search_space` | Dimensions varied per trial — add values or move from `fixed_params` to expand search |
| `fixed_params` | All other tunable dimensions: `news_weight`, `max_single_position_weight`, `master_score_weights`, `risk_pct`, `atr_multiplier`, `rolling_window` |

Other configs (referenced by `fixed_params` for source traceability):

| File | Purpose |
|------|---------|
| `config/model_config.yaml` | Training/OOS dates (machine-written — do not edit) |
| `config/strategy_params.yaml` | Auto-promoted winner params |
| `config/trading_config.yaml` | Execution settings |
| `config/technical_master_score.yaml` | Indicator definitions and category weights |
| `config/data_config.yaml` | Universe watchlist, data paths |

---

## Project Structure

```
ai_supply_chain_trading/
├── config/
│   ├── data_config.yaml             # Universe watchlist, data source paths
│   ├── model_config.yaml            # Rolling training window (machine-written)
│   ├── optimizer_config.yaml        # Random-search optimizer settings
│   ├── strategy_params.yaml         # Auto-promoted winner params
│   ├── technical_master_score.yaml  # Master Score category weights
│   └── trading_config.yaml          # Execution + risk limits
├── scripts/
│   ├── run_e2e_pipeline.py          # Canonical E2E entry point (5 stages)
│   ├── run_optimizer.py             # Autonomous random-search optimizer
│   ├── run_promoter.py              # Promotes winner → strategy_params.yaml
│   ├── run_factory.py               # ML model factory (rolling window patch)
│   ├── run_execution.py             # Portfolio execution (mock/paper)
│   ├── run_weekly_rebalance.py      # Standalone weekly rebalance
│   ├── backtest_technical_library.py # Canonical backtest engine
│   ├── update_price_data.py         # Price data refresh
│   └── update_news_data.py          # News data refresh
├── src/
│   ├── core/
│   │   ├── signal_engine.py         # Signal orchestration
│   │   ├── policy_engine.py         # Regime & policy gates
│   │   └── portfolio_engine.py      # HRP/ATR construction + max-weight cap
│   ├── signals/
│   │   ├── technical_library.py     # Master Score (4 categories)
│   │   └── news_engine.py           # News Alpha (4 strategies)
│   └── data/
│       └── csv_provider.py          # Price CSV loader
├── outputs/
│   ├── e2e_oos_backtest.json        # Latest OOS backtest result
│   ├── last_valid_weights.json      # Latest portfolio weights
│   └── optimizer_results.json       # Full optimizer trial log
├── models/
│   └── factory_winner.json          # Best model from last factory run
└── docs/                            # Canonical documentation (see INDEX.md)
```

---

## Data Location

All trading data lives **outside the repo** at `C:\ai_supply_chain_trading\trading_data\`:

- Price CSVs: `trading_data\stock_market_data\{nasdaq,sp500,nyse,forbes2000}\csv\`
- News (Marketaux flat): `trading_data\news\{ticker}_news.json`
- Tiingo parquets: `trading_data\news\tiingo_{YYYY}_{MM}.parquet`

Set `DATA_DIR=C:\ai_supply_chain_trading\trading_data` in `.env`.

---

## Signal Generation

### Master Score (Technical)

- 40% Trend (MACD, ADX, PSAR, Aroon, moving averages)
- 30% Momentum (Stochastic, CCI, Williams %R, ROC, RSI)
- 20% Volume (OBV, CMF, VWAP, volume ratio)
- 10% Volatility (Bollinger Bands, ATR, Keltner)

### News Alpha (4 Strategies)

- A: Buzz — Z-score of article volume
- B: Surprise — Sentiment delta vs 30-day baseline (1-day lag)
- C: Sector Relative — Cross-sectional ranking
- D: Event-Driven — Catalyst detection (earnings, M&A, FDA)

Composite: `(1 - news_weight) × Tech_Score + news_weight × News_Composite`

### ML Model Factory

Random Forest trained on rolling 4-year window with TimeSeriesSplit CV.
Features: `momentum_avg`, `volume_ratio_norm`, `rsi_norm`.
News features neutral (0.5) for pre-2025 training rows (no historical backfill available).

---

## Risk Controls

| Control | Implementation |
|---------|---------------|
| Max single position weight | `trading_config.yaml` → `risk.max_single_position_weight: 0.40` |
| Dual-confirmation cash-out | BEAR regime + SPY < 200-SMA → 100% cash |
| Sideways scaling | Position × 0.5 in SIDEWAYS regime |
| Daily risk exit | Exit if return ≤ threshold |
| OOS Sharpe gate | Optimizer rejects trials with Sharpe < `min_sharpe` |
| Atomic writes | All output files written via `.tmp` → rename |

---

## Regime Detection (3-State HMM)

- BULL (high mean, low vol) → aggressive weights
- BEAR (low mean, high vol) → defensive + CASH_OUT if SPY < 200-SMA
- SIDEWAYS (mean ≈ 0) → balanced, position × 0.5

---

## Current Status (2026-04-12)

| Capability | Status |
|-----------|--------|
| Dynamic data ingestion (price + news) | ✅ Complete |
| Rolling ML model training | ✅ Complete |
| OOS backtest with contamination guard | ✅ Complete |
| Portfolio construction (HRP + max-weight cap) | ✅ Complete |
| Mock execution + weight output | ✅ Complete |
| E2E pipeline (`run_e2e_pipeline.py`) | ✅ Complete |
| Autonomous optimizer (`run_optimizer.py`) | ✅ Complete |
| Config promotion (`run_promoter.py`) | ✅ Complete |
| Auto-scheduler (Windows Task Scheduler) | ✅ Complete |
| Live IBKR prices + account data (`ibkr_live_provider.py`) | ✅ Built — activate with TWS |
| Multi-instrument contracts (`contract_resolver.py`) | ✅ Built — equity, futures (NQ/MNQ), options (SMH) |
| Futures-aware position sizing (multiplier in quantity calc) | ✅ Complete |
| Paper order submission (`--confirm-paper`) + fill ledger | ✅ Built — activate with TWS |
| First live paper run validation | ⚠️ Deferred — requires TWS running |
| Real-time streaming prices | ❌ Not implemented (using snapshots) |

---

## Canonical Documentation

See `docs/INDEX.md` for the full documentation index.

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | System design and data flow |
| `docs/WORKFLOW.md` | Execution stages |
| `docs/STRATEGY_LOGIC.md` | Capital decision logic |
| `docs/DECISIONS.md` | Architectural decision records |
| `docs/BACKTEST_JOURNAL.md` | Backtest results and safety audits |
| `docs/PROJECT_STATUS.md` | Current state and readiness |

**For AI agents:** See `AI_RULES.md` and `.cursorrules`.

---

## Key Dependencies

```bash
# Core
pip install pandas numpy pyyaml python-dotenv

# Signals + portfolio
pip install pandas-ta PyPortfolioOpt hmmlearn scikit-learn

# News sentiment
pip install transformers spacy python-Levenshtein
python -m spacy download en_core_web_md

# Execution (IBKR, optional)
pip install ib_insync
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values. `DATA_DIR` is required; all others are optional depending on which pipeline stages you run.

| Variable | Required | Description |
|----------|----------|-------------|
| `DATA_DIR` | Yes | Absolute path to trading data root (`C:\ai_supply_chain_trading\trading_data`) |
| `GOOGLE_API_KEY` | Yes (pipeline) | Google/Gemini key — sentiment scoring and supply chain analysis |
| `MARKETAUX_API_KEY` | Yes (pipeline) | Live weekly rebalance news source |
| `TIINGO_API_KEY` | Yes (news) | 2025-present news data; live ticker tagging |
| `FMP_API_KEY` | Optional | Fundamentals (20-quarter FCFF pipeline); Starter plan required |
| `EODHD_API_KEY` | Optional | News backfill and non-US price refresh |
| `EDGAR_IDENTITY` | Optional | SEC identity string (`"Name email"`) for 10-K XBRL audit checks |
| `IBKR_HOST` | Optional | TWS host (default `127.0.0.1`) |
| `IBKR_PORT` | Optional | TWS port (default `7497` for paper, `7496` for live) |

---

## License

[Your License Here]
