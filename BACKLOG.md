# BACKLOG — Known Issues & Deferred Items

> Single source of truth for all known issues, deferred tasks, and open questions.
> Updated: 2026-03-17

---

## 🔴 Blocking

| # | Issue | File | Notes |
|---|-------|------|-------|
| B1 | `sklearn ImportError` in `wealth` env | `scripts/train_ml_model.py` | Blocks model retraining and Final Truth backtest runs |

---

## 🟠 Architecture / Strategy

| # | Issue | File | Notes |
|---|-------|------|-------|
| A1 | Extension pod suppresses gross in bull regime (`net_exposure=0.555`) | `pods/pod_extension.py`, `pods/aggregator.py` | Root cause: Track D shorts cancel long-side gains in bull year. Fix = regime-gate shorts so S>0 only when regime=EMERGENCY. In NORMAL, Extension collapses to leveraged long-only |
| A2 | Track D individual-stock shorts structurally broken for sector-concentrated bull universe | `pods/pod_extension.py` | 2023 backtest: Sharpe=-0.10, return=-71.9%, MDD=-90.3%. Even bottom-ranked AI/semi names go up in bull years. SME decision pending on whether to abandon shorts or gate by regime |
| A3 | `pod_fitness.json` bootstrapped from 2024 OOS baselines, not live history | `pods/meta_allocator.py`, `outputs/pod_fitness.json` | Meta-allocator weights will only become meaningful once live rebalance history accumulates. Need update mechanism post each weekly rebalance |

---

## 🟡 Data / Config

| # | Issue | File | Notes |
|---|-------|------|-------|
| D1 | `SPY nan` and `SMH +nan%` in regime_monitor output | `scripts/regime_monitor.py` | yfinance returning NaN for SPY close and SMH daily return. Regime still triggers correctly via Z-score fallback but display is wrong |
| D2 | `target_vol: 0.40` in `model_config.yaml` keeps being silently reverted to `0.15` by linter | `config/model_config.yaml` | Currently set to 0.40. Watch after any lint/format pass |
| D3 | Supply chain `relationships.json` not in repo | `src/signals/sentiment_propagator.py` | Propagation silently disabled when file missing. No warning logged |
| D4 | `6758.T` (Sony) hits 40% liquidity cap consistently | `src/portfolio/position_manager.py` | Consider lowering global ceiling or excluding from liquidity cap logic |

---

## 🟡 Backtests / Validation

| # | Issue | File | Notes |
|---|-------|------|-------|
| V1 | Final Truth 3-year table (2022–2024) not complete | `scripts/generate_final_truth_table.py` | Requires B1 (sklearn) to be resolved first |
| V2 | E2E paper trading round-trip not validated | `scripts/run_execution.py` | Requires TWS running with live fills; fill reconciliation not yet tested end-to-end |
| V3 | Last-week return anomaly in backtests (-21% to -23%) | `scripts/backtest_technical_library.py` | Persistent across static and dynamic Track D. Likely data issue on final week boundary |

---

## 🟡 Risk Management (New — 2026-03-17)

| # | Issue | File | Notes |
|---|-------|------|-------|
| R1 | `misalignment=critical` fires immediately on fresh install | `src/monitoring/structural_breakdown.py` | All pods show beta=1.268 because `last_valid_weights.json` holds single-spine weights, not pod-specific weights. Will normalise once `--pods` path accumulates multi-week history |
| R2 | FutureWarning: mixed timezone parsing in csv_provider.py | `src/data/csv_provider.py` | Pandas will error in a future version. Fix: add `utc=True` to `pd.to_datetime` calls at lines 66 and 91 |

---

## 🟢 Deferred (Low Priority / BAU)

| # | Issue | Notes |
|---|-------|-------|
| L1 | Quarterly model retraining not automated | Currently manual via `train_ml_model.py` |
| L2 | `pod_fitness.json` not updated after weekly rebalance | Need to wire Sharpe/MDD tracking into `run_weekly_rebalance.py` |
| L3 | Live trading sign-off | Awaiting fill reconciliation validation with real TWS fills |
| L4 | Regime watcher Windows Task Scheduler registration | One-time admin step; not yet done |
