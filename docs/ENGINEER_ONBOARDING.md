# AI Supply Chain Trading System — Engineer Onboarding Guide

> Generated: 2026-03-17. Review against `docs/INDEX.md` for latest architecture changes.

---

## 1. OVERVIEW

A quantitative trading system for a 47-ticker AI/semiconductor supply chain universe. Generates weekly portfolio rebalance signals by combining a technical Master Score (20 indicators), optional news sentiment alpha (EODHD/Tiingo/Marketaux), a CatBoost ML blend, and a 3-state regime gate. Executes via IBKR paper account (DUM879076, SGD, NAV ~1M SGD). Built for a single-operator HNWI trading desk — not a multi-user platform.

---

## 2. REPO STRUCTURE

```
ai_supply_chain_trading/
├── config/                    # All tunable parameters (YAML)
├── scripts/                   # Entry points (25+ scripts)
├── src/                       # Core library (12 packages, 79 files)
│   ├── core/                  # Spine: target_weight_pipeline.py
│   ├── signals/               # Master Score, news engine, ML feature factory
│   ├── models/                # CatBoost/Ridge/XGBoost training + factory
│   ├── portfolio/             # HRP optimizer, long/short, position sizing
│   ├── execution/             # IBKR bridge, order submission
│   ├── data/                  # CSV provider, EODHD/Tiingo loaders
│   └── monitoring/            # Telegram alerts, regime watcher daemon
├── models/saved/              # Trained model .pkl files
├── outputs/                   # Audit logs, regime_status.json, backtests
└── docs/                      # 11 architecture/spec docs (read INDEX.md first)
```

**Key config files:**

| File | Controls |
|------|---------|
| `config/universe.yaml` | 47-ticker universe, IBKR symbol mappings |
| `config/model_config.yaml` | Active ML model, feature names, Track D params |
| `config/technical_master_score.yaml` | Indicator weights, regime weights, news_weight |
| `config/strategy_params.yaml` | Propagation, LLM triggers, rebalance schedule |

**Entry points:**

| Script | Purpose |
|--------|---------|
| `scripts/backtest_technical_library.py` | Research backtest (`--start/--end/--track/--no-llm`) |
| `scripts/run_weekly_rebalance.py` | Automated weekly rebalance (calls run_execution.py) |
| `scripts/run_execution.py` | Live/paper execution spine |
| `scripts/train_ml_model.py` | Retrain CatBoost/Ridge (`--residual`) |
| `scripts/regime_monitor.py` | Output `outputs/regime_status.json` |
| `scripts/dashboard.py` | Streamlit HNWI dashboard (auto-refresh 30s) |

---

## 3. EXECUTION FLOW

### Weekly Rebalance (Production)
```
run_weekly_rebalance.py
  → update_price_data.py          # fetch OHLCV
  → update_news_data.py           # fetch Marketaux
  → run_execution.py
      → regime_monitor.py         # VIX/SPY/SMH z-scores → regime_status.json
      → load prices + news        # CSV provider + EODHD/Tiingo loader
      → model factory (7d cache)  # select best model
      → target_weight_pipeline.compute()
          → SignalEngine           # Master Score + news blend
          → PolicyEngine           # regime gates (CASH_OUT, size × 0.5)
          → PortfolioEngine        # HRP + alpha tilt + EWMA vol
          → PositionManager        # compute delta shares
          → IBExecutor             # submit orders (paper or mock)
```

### Backtest (Research)
```
backtest_technical_library.py --start ... --end ... --track D --no-llm
  For each week:
    → prices sliced strictly <= week_date (no look-ahead)
    → SignalEngine (same as production)
    → Optional ML blend (0.7 base + 0.3 model)
    → Track D: rebalance_alpha_sleeve() → dynamic short sleeve
    → Simulate next-day open entry, 15 bps friction
  Output: sharpe, total_return, max_drawdown, gross_exposure_avg
```

### Model Training (Monthly)
```
train_ml_model.py --residual
  → load prices + EODHD news (2022–2024)
  → compute 20 indicators → feature matrix
  → target = stock_return − rolling_beta × SMH_return
  → walk-forward IC evaluation
  → save winner to models/saved/catboost_*.pkl
```

---

## 4. CORE METHODOLOGY

**Master Score** (always-on, 100% weight when no ML):
```
Trend(40%) + Momentum(30%) + Volume(20%) + Volatility(10%)
Each sub-score = mean of normalized indicators in that category (missing → 0.5 neutral)
Result: [0, 1] per ticker per week
```

**ML Blend** (30% weight, CatBoost IC=0.0428):
```
final_score = 0.7 × master_score + 0.3 × catboost_prediction
Target: residual return (stock return − 60d beta × SMH return)
Features: rsi_norm, sentiment_velocity, news_sentiment, cmf_norm, macd_norm
```

**Portfolio Construction** (HRP + Alpha Tilt):
```
HRP weights (60d returns, ward linkage) → alpha tilt by score → EWMA vol scale → liquidity cap
```

**Regime Gate** (policy, not score modifier):
```
BEAR + SPY < 200-SMA → 100% cash
SIDEWAYS → position size × 0.5
BULL → full exposure
```

**Track D — Dynamic Alpha-Sleeve:**
```
Short exposure S ∈ [0, 0.30] based on cross-sectional dispersion
S = 0 when long/short basket correlation ρ > 0.70 (bull momentum gate)
Leverage multiplier = min(target_vol / realised_vol_20d, 1.6)
target_vol = 0.40 (semi stocks ~40-50% annualised vol)
```

---

## 5. DATA & DEPENDENCIES

**Data sources:**

| Source | Coverage | Use |
|--------|---------|-----|
| Price CSVs (`trading_data/stock_market_data/`) | 2021–present | All workflows |
| EODHD parquet (`trading_data/news/eodhd_global_backfill.parquet`) | 2022–2024, 236k rows | Backtest news |
| Tiingo parquets (`trading_data/news/tiingo_YYYY_MM.parquet`) | 2025+ | Live news |
| Marketaux JSON (`trading_data/news/{ticker}_news.json`) | 2025+ | Live rebalance |
| SMH ETF (`trading_data/benchmarks/SMH.csv`) | 2021–2024 | Regime + beta |

**Trading data root:** `C:\ai_supply_chain_trading\trading_data\` (env var `DATA_DIR` in `.env`)
Not in git — lives on a separate drive.

**Critical dependencies:**
- `numpy < 2.3` (pandas-ta compatibility)
- `fastparquet` — required for all parquet ops (pyarrow crashes on Windows/Anaconda)
- `PyPortfolioOpt` — HRP optimizer
- `catboost` — active ML model (not in requirements.txt; install separately)
- `scikit-learn` — currently broken in `wealth` env (blocks training scripts)

**API keys needed** (in `.env`): `GOOGLE_API_KEY`, `MARKETAUX_API_KEY`, `TIINGO_API_KEY`, `EODHD_API_KEY`

---

## 6. ASSUMPTIONS & DESIGN CHOICES

**Explicit:**
- Tiingo historical API is broken (all dates return ~2025-11-xx) — confirmed, documented in CLAUDE.md
- Pre-2025 news features default to 0.5 neutral for training
- EODHD sentiment is heavily skewed toward 1.0 — requires cross-sectional z-score normalization
- No same-day execution — always next-day open
- `fastparquet` only on Windows (not pyarrow)

**Implicit:**
- Universe is highly correlated (all AI/semi sector) — shorting bottom-ranked names in bull years destroys value
- Individual stock vol (~40-60% ann) >> portfolio vol (~25-35%) — vol throttle must use `prior_weights` feedback to estimate portfolio-level vol, not individual stock means
- HRP assumes returns are stationary over 60-day window
- Regime gate is binary (BULL/SIDEWAYS/BEAR) — no gradual exposure ramp

**Trade-offs:**
- Technical-first over news-first: news unreliable for pre-2025, so deliberately secondary
- Weekly cadence trades off alpha decay against transaction costs
- 30% ML blend is conservative — preserves interpretability of base signal

---

## 7. CONFIGURATION & EXTENSIBILITY

| Change | Where |
|--------|-------|
| Add ticker | `config/universe.yaml` → run `scripts/sync_universe.py` → ensure CSV in `trading_data/` |
| Add indicator | `technical_library.calculate_all_indicators()` → `config/technical_master_score.yaml` → `FEATURE_REGISTRY` |
| Change ML model | `active_model:` in `config/model_config.yaml` → retrain |
| Change regime weights | `BULL_WEIGHTS` / `DEFENSIVE_WEIGHTS` in `config/technical_master_score.yaml` |
| Change news weight | `news_weight: 0.20` in `config/technical_master_score.yaml` |
| Tune Track D | `config/model_config.yaml tracks.D` block (target_vol, max_leverage, top_n, bottom_n, dispersion_anchor) |

---

## 8. RISKS / GAPS

**Blocking:**
- `sklearn ImportError` in `wealth` env — blocks `train_ml_model.py` and Final Truth backtest runs

**Fragile:**
- `except Exception: return {}` pattern in `eodhd_news_loader.py` and `news_fetcher_factory.py` — errors silently swallowed
- `pandas-ta` requires `numpy.NaN` patch at `technical_library.py:18` — breaks if numpy version changes
- `target_vol` in `config/model_config.yaml` was silently reverted by linter twice — watch this value

**Structural gaps:**
- Track D individual-stock shorts are structurally unsuitable for a sector-concentrated bull universe
  - 2023 backtest: Sharpe=-0.102, return=-71.9%, MDD=-90.3%
  - 2024 backtest: Sharpe=+0.206, return=+133.5%, MDD=-23.3%
  - In bull years, even bottom-ranked AI/semi names go up — short book consistently loses
- No automatic model retraining schedule — manual only
- Supply chain `relationships.json` not in repo — propagation silently disabled if missing
- No portfolio-level VaR — regime is a binary gate, not a continuous risk input
- `6758.T` hits 40% liquidity cap consistently

**Deferred:**
- Final Truth 3-year table (2022–2024) not yet complete
- E2E paper trading round-trip not validated with live TWS fills
- Quarterly model retraining not automated

---

## 9. QUICK START

```bash
# 1. Activate environment
conda activate wealth

# 2. Ensure .env exists with DATA_DIR=C:/ai_supply_chain_trading/trading_data

# 3. Quick sanity backtest (2024, no ML, no LLM)
python scripts/backtest_technical_library.py \
    --start 2024-01-01 --end 2024-12-31 \
    --no-llm --no-ml

# 4. Track A (with CatBoost ML)
python scripts/backtest_technical_library.py \
    --start 2024-01-01 --end 2024-12-31 \
    --track A --no-llm

# 5. Track D (Dynamic Alpha-Sleeve)
python scripts/backtest_technical_library.py \
    --start 2024-01-01 --end 2024-12-31 \
    --track D --no-llm

# 6. Check regime
python scripts/regime_monitor.py

# 7. Dry-run rebalance
python scripts/run_weekly_rebalance.py --dry-run

# 8. Dashboard
streamlit run scripts/dashboard.py
```

---

## 10. BACKTEST BASELINES (as of 2026-03-17)

### Baseline — Long-Only, No ML
| Year | Sharpe | Return | MDD |
|------|--------|--------|-----|
| 2022 | -0.077 | -6.1% | -9.0% |
| 2023 | +0.365 | +59.2% | -10.1% |
| 2024 | +0.526 | +148.6% | -9.4% |

### Alpha — Long-Only, CatBoost 0.3× blend
| Year | Sharpe | Return | MDD | Note |
|------|--------|--------|-----|------|
| 2022 | +0.247 | +53.1% | -13.1% | ⚠️ partially in-sample |
| 2023 | +0.410 | +72.9% | -9.5% | |
| 2024 | +0.564 | +186.3% | -8.8% | ✅ true OOS |

### Track D — Dynamic Alpha-Sleeve (target_vol=0.40, EODHD news)
| Year | Sharpe | Return | MDD | Note |
|------|--------|--------|-----|------|
| 2023 | -0.102 | -71.9% | -90.3% | ❌ short book destroyed by bull market |
| 2024 | +0.206 | +133.5% | -23.3% | ρ gate suppressed shorts most of year |
