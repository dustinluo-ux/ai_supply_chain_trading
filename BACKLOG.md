# BACKLOG — Known Issues & Deferred Items

> Single source of truth for all known issues, deferred tasks, and open questions.
> Updated: 2026-03-18

---

## 🔴 Blocking

_None currently._

---

## 🟡 Backtests / Validation

| # | Issue | File | Notes |
|---|-------|------|-------|
| V2 | E2E paper trading round-trip not validated | `scripts/run_execution.py` | Requires TWS running with live fills; fill reconciliation not yet tested end-to-end |
| V3 | Last-week return anomaly in backtests (-21% to -23%) | `scripts/backtest_technical_library.py` | Persistent across static and dynamic Track D. Likely data issue on final week boundary. Investigation deferred. |

---

## 🟡 Data / Config

| # | Issue | File | Notes |
|---|-------|------|-------|
| D2 | `target_vol: 0.40` in `model_config.yaml` silently reverted to `0.15` by linter | `config/model_config.yaml` | Currently 0.40. Watch after any lint/format pass. |
| D4 | `6758.T` (Sony) hits 40% liquidity cap consistently | `src/portfolio/position_manager.py` | SME decision pending on whether to lower global ceiling or exclude from cap logic. |

---

## 🟢 Deferred (Low Priority / BAU)

| # | Issue | Notes |
|---|-------|-------|
| L1 | Quarterly model retraining not automated | Currently manual via `train_ml_model.py` |
| L3 | Live trading sign-off | Awaiting fill reconciliation validation with real TWS fills |
| L4 | Regime watcher Windows Task Scheduler registration | One-time admin step; not yet done |

---

## ✅ Resolved (this sprint — 2026-03-18)

| # | Issue | Resolution |
|---|-------|------------|
| A1 | Extension pod suppresses gross in bull regime | Track D FSM State B collapses to SMH ETF hedge when SPY > 200-SMA or correlation high |
| A2 | Track D individual-stock shorts broken in bull universe | Bayesian skeptical prior lowers rho threshold to 0.65 in bull; State C exits shorts entirely when IC < 0 |
| A3 | `pod_fitness.json` bootstrapped from static 2024 baselines | Live feedback loop: `pod_pnl_tracker.py` computes rolling Sharpe/MDD from fills and updates fitness after each run |
| B1 | `sklearn ImportError` in `wealth` env | sklearn 1.7.2 confirmed present — stale entry |
| D1 | SPY/SMH NaN display in `regime_monitor` output | `math.isfinite()` guards added to print block and JSON output |
| D3 | `relationships.json` missing — propagation silently disabled | `logger.warning` added to `SupplyChainManager._load_database()` |
| L2 | `pod_fitness.json` not updated after weekly rebalance | `update_pod_fitness()` wired into `run_execution.py --pods` post-execution |
| R1 | `misalignment=critical` fires on fresh install | Minimum 3 weight snapshots required before misalignment escalates beyond "ok" |
| R2 | FutureWarning: mixed timezone parsing in csv_provider.py | `csv_provider.py` lines 91–92 already apply `utc=True` — stale entry |
