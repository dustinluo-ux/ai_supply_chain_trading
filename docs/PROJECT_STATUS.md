# PROJECT STATUS — Current State & Readiness Assessment

**Last Updated:** 2026-04-16
**Project:** AI Supply Chain Quantitative Trading System
**Phase:** MVP Complete — Autonomous E2E Pipeline Operational

---

## Executive Summary

Autonomous quantitative trading pipeline for the AI/semiconductor supply chain universe (54 tickers). The full chain from raw data to promoted config runs unattended: weekly parameter optimization, quarterly model retraining, and paper execution via IBKR TWS — all self-scheduled via Windows Task Scheduler.

**Current OOS backtest result (2024, optimized params):**

| Mode | Sharpe | CAGR | MDD |
|------|--------|------|-----|
| Technical only (top_n=3) | 0.609 | +90.0% | -9.4% |
| ML blend (top_n=3) | 0.704 | +145.2% | -13.5% |
| Technical only (top_n=5) | 0.771 | +116.4% | -7.5% |
| ML blend (top_n=5) | 0.695 | +133.5% | -13.5% |

**ML consistently adds +15-30% CAGR** at the cost of ~6% additional drawdown. Winning optimizer params: sma_window=100, score_floor=0.65, top_n=3 (IS Calmar 1.683, OOS 2024 Calmar 9.67).

---

## What Works

### Autonomous Pipeline

| Component | Status | Notes |
|-----------|--------|-------|
| Stage 1: Data refresh | Complete | `update_price_data.py` + `update_news_data.py`; skip with `--skip-data` |
| Stage 2: ML factory | Complete | Rolling 4-yr window; CatBoost IC=0.0958; `factory_winner.json` written atomically |
| Stage 3: OOS backtest | Complete | `e2e_oos_backtest.json` written atomically |
| Stage 3.5: Skeptic Gate | Complete | Bear-flag screen; WEIGHT_TRIGGER=0.15; >=2 flags = FAIL; skipped during optimizer trials |
| Stage 3.6: Agent Audit | Complete | Taleb + Damodaran advisory; `agent_audit.json`; never exits non-zero |
| Stage 4: Execution | Complete | Mock (default) or paper (`--no-dry-run --ibkr-port 7497`) |
| Stage 5: Summary | Complete | ASCII STATUS: PASS/WARN/FAIL + exit code |
| Weekly optimizer | Complete | Random search over search_space; promotes winner; auto-schtasks next Monday 06:00 |
| Quarterly retrain | Complete | Force retrain + OOS gate + promotion gate; auto-schtasks 91 days out |
| Config promotion | Complete | `run_promoter.py` skips if composite <= -998 or exit_code != 0 |
| RiskOverlay | Complete | Tier1/Tier2/Tier3; VIX threshold=28; SPY SMA=100; wired into `run_weekly_rebalance.py` |
| Drawdown tracker | Complete | `outputs/drawdown_tracker.json`; stop-loss at -10%; FLATTEN ALL |
| Fill ledger | Complete | `outputs/fills/fills.jsonl`; appended on every order (mock + paper) |

### Signal Stack

- Master Score: Trend 40% / Momentum 30% / Volume 20% / Volatility 10%
- CatBoost ML blend: ml_blend_weight=0.3; IC=0.0958; 5 features (rsi_norm, sentiment_velocity, news_sentiment, cmf_norm, macd_norm)
- Portfolio construction: HRP + Alpha Tilt; EWMA vol (lambda=0.94); max single position 0.40
- News: Pre-2025 neutral (0.5); 2025+ via Tiingo (requires TIINGO_API_KEY in .env)
- Regime: Z-score gate; score_floor_contraction=0.65

### Three-Layer Signal Engine (feature-flagged, off by default)

A new signal architecture lives alongside the existing pipeline in `src/signals/layered_signal_engine.py`. Enable via `strategy_params.use_layered_engine: true`.

- **Layer 3 (technical/sentiment):** cross-sectional z-score → percentile rank for 9 signals (rsi_norm, macd_norm, cmf_norm, momentum_avg, volume_ratio_norm, news_sentiment, news_supply, sentiment_velocity, news_spike). Equal-weight composite.
- **Layer 2 (fundamental cycle):** cross-sectional z-score → percentile rank for earnings_revision_30d, gross_margin_pct, inventory_days (negated), TES score. Quarterly cadence; forward-filled up to 91 days with `l2_stale` flag. Falls back to Layer 3 when <60% universe has non-stale data.
- **Layer 1 (post-signal caps only):** FCF + leverage quality filter (zero-out); post-earnings miss dampener (×0.7 within 5 days of >10% miss); pre-earnings size-down (×0.5 within 2 days); macro-regime multiplier from yield curve slope (EXPANSION ×1.0 / LATE_CYCLE ×0.7 / CONTRACTION ×0.4).
- **Combination:** `w = 0.6 × Layer2_pseudo_weight + 0.4 × Layer3_pseudo_weight`, then net-zero normalize (±1.0 long-short convention).
- **Data feed:** `scripts/fetch_quarterly_fundamentals.py` — `--mode quarterly` full fetch, `--mode weekly` refreshes earnings_revision_30d only. Output: `trading_data/fundamentals/quarterly_signals.parquet`.
- **Config:** `config/layered_signal_config.yaml` — all weights, thresholds, and multipliers tunable without code changes.

### Execution Infrastructure

- IBKR TWS: paper account DUM879076 (SGD); port 7497
- Contract resolver: equity / NQ future (x20) / MNQ (x2) / SMH options (ATM, 30 DTE)
- Circuit breaker, AccountMonitor, OrderDispatcher wired
- `--confirm-paper` submits real orders via IBExecutor

---

## Known Gaps (Non-Blocking for Paper Trading)

| Gap | Impact | Mitigation |
|-----|--------|------------|
| Live paper orders never submitted | Skeptic Gate correctly blocked AMD/TSM (bear flags as of 2026-04-13); will clear when flags resolve | Run `run_e2e_pipeline.py --skip-data --no-dry-run --ibkr-port 7497` when gate passes |
| schtasks registration unverified | Silent warn on privilege failure | Check Task Scheduler manually after first run |
| Tiingo news not wired by default | 2025+ news not used in live signal unless configured | Set `news.source: tiingo` + TIINGO_API_KEY in .env |
| min_order_size / max_position_size not enforced in executor | Oversized orders possible | Hard cap at max_single_position_weight=0.40 is enforced in portfolio engine |
| No fill reconciliation | No expected-vs-actual position check | Manual check via `--check-fills` flag |

---

## Canonical Entry Points

```
scripts/run_e2e_pipeline.py         # Full pipeline (5 stages)
scripts/run_optimizer.py            # Weekly autonomous optimizer
scripts/run_quarterly_retrain.py    # Quarterly model retrain + promotion gate
scripts/run_promoter.py             # Promote optimizer winner to strategy_params.yaml
scripts/run_weekly_rebalance.py     # Standalone weekly rebalance (RiskOverlay wired)
scripts/run_execution.py            # Execution spine (mock / paper / live)
scripts/backtest_technical_library.py  # Standalone OOS backtest engine
scripts/train_ml_model.py           # Manual ML retrain
scripts/fetch_quarterly_fundamentals.py  # EODHD fundamental signals (--mode quarterly|weekly)
```

---

## Key Output Artifacts

| File | Purpose |
|------|---------|
| `outputs/e2e_oos_backtest.json` | Latest OOS backtest result |
| `outputs/last_valid_weights.json` | Latest portfolio weights |
| `outputs/optimizer_results.json` | Full optimizer trial log |
| `outputs/retrain_oos_latest.json` | Latest quarterly retrain OOS result |
| `outputs/retrain_baseline.json` | Retrain promotion baseline (Sharpe + CAGR) |
| `outputs/agent_audit.json` | Taleb + Damodaran per-ticker advisory |
| `outputs/fills/fills.jsonl` | Order fill ledger |
| `outputs/drawdown_tracker.json` | Peak NAV, current drawdown, flatten_active |
| `outputs/risk_metadata_history.csv` | Weekly RiskOverlay log |
| `models/factory_winner.json` | Best model from last factory run |
| `trading_data/fundamentals/quarterly_signals.parquet` | EODHD fundamental signals for layered engine (earnings revision, gross margin, inventory, FCF, leverage) |

---

## Promoted Parameters (as of 2026-04-12)

From `config/strategy_params.yaml`:
- `optimizer_promotion.top_n`: 3
- `optimizer_promotion.score_floor`: 0.65
- `optimizer_promotion.sma_window`: 100
- `risk_overlay.vix_elevated_threshold`: 28
- `risk_overlay.spy_sma_window`: 100
- `risk_overlay.vix_multiplier`: 0.6
- `regime.score_floor_contraction`: 0.65

---

## Readiness Assessment

| Capability | Status |
|-----------|--------|
| Autonomous backtesting | 100% complete |
| Weekly parameter optimization | 100% complete |
| Quarterly model retraining | 100% complete |
| Mock execution | 100% complete |
| Paper execution (IBKR) | 95% complete — pending first live order |
| Live trading | 20% complete — pending paper validation, real-time feeds, reconciliation |

**Next gate:** Submit first paper order when Skeptic Gate clears (AMD/TSM bear flags resolve).
**Beyond that:** Position reconciliation, fill verification, live trading sign-off.
