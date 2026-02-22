# Regime Management

This document describes the regime logic used for portfolio construction and intraweek risk control: volatility-adjusted alpha tilt, macro emergency brake, weekly rebalance lock, and the decision record for the emergency brake.

---

## 1. Volatility-Adjusted Alpha Tilt

**Formula:** Raw weight per ticker is proportional to **score / volatility** (30-day rolling vol). We then normalize so weights sum to 1 and apply a per-ticker cap.

**Eligibility gate:** A ticker is eligible only if:

- **Score** > max( **top_quartile**, **floor** ), where:
  - **top_quartile** = 75th percentile of all scored tickers (configurable).
  - **floor** = dynamic, set by `regime_monitor.py` based on SPY 200-SMA:
    - **BULL** (SPY ≥ 200-SMA): floor = **0.50** — normal entry threshold
    - **BEAR** (SPY < 200-SMA): floor = **0.65** — raised entry hurdle, fewer names qualify

The SPY 200-SMA gate therefore serves **dual purpose**: it is both the *entry hurdle* (score floor) during normal operation and the *emergency exit* trigger when combined with VIX > 30 or SMH -5%. In BEAR regime, the system naturally concentrates into only the highest-conviction names — or holds cash entirely if none clear the 0.65 bar.

`regime_monitor.py` is the single source of truth for `score_floor`. It writes the value to `outputs/regime_status.json`, which `portfolio_optimizer.py` reads at runtime. If `regime_status.json` is absent, the optimizer falls back to its own independent SPY 200-SMA check.

**25% cap with iterative redistribution:** No single ticker may have weight above the configured maximum (e.g. 25%). If any ticker exceeds the cap, its weight is set to the cap and the excess is redistributed proportionally to the remaining (uncapped) tickers; this is repeated until no weight exceeds the cap. If all tickers are capped, redistribution stops.

**Rationale:** The tilt preserves signal magnitude (higher score and lower vol get more weight) while naturally risk-adjusting without binary exclusion. The cap limits concentration; the floor and regime-specific floors avoid loading up on marginal names.

---

## 2. Macro Emergency Brake (Mid-Week Liquidation)

**Triggers (any one is sufficient):**

1. **VIX > 30** — elevated fear / volatility regime.
2. **SPY < 200-day SMA** — broad market below long-term trend.
3. **SMH daily return < -5%** — severe single-day drop in the semiconductor/supply-chain sector.

**Action:** Full liquidation to cash and freeze rebalancing until the next Monday. No new equity positions until the next weekly rebalance window.

**Rationale:** The AI/semiconductor supply-chain universe (this 47-ticker set) has high average pairwise correlation (~0.75+) during sector shocks. In such conditions:

- A SMH -5% day or a VIX > 30 spike tends to invalidate the week’s cross-sectional signal.
- Re-weighting within the same correlated universe does not provide meaningful diversification.
- Cash is the only clear hedge; the emergency brake implements that defensively.

---

## 3. Weekly Lock

**Monday-only rebalance window:** Target weights and execution are updated only on Mondays (after the optimizer runs). Tuesday–Friday are **monitor-only** days: we run the regime monitor and may trigger the emergency brake, but we do not re-run the optimizer or send new rebalance orders.

**Rationale:** The ML model’s forward return horizon is 5 business days. Rebalancing once per week aligns with that horizon and avoids overtrading on intraweek noise. The weekly lock enforces this discipline.

---

## 4. Decision Log D023 — Macro Emergency Brake

**Decision:** Adopt a **macro emergency brake** that, when triggered (VIX > 30, SPY < 200-SMA, or SMH daily return < -5%), moves the portfolio to full cash and locks rebalancing until the next Monday.

**Alternatives considered:**

- **(a) Reduce position sizes proportionally to VIX** — Rejected: adjustment would be too slow and still leave exposure in a correlated universe during a shock.
- **(b) Hedge with inverse ETFs** — Rejected: adds basis risk and requires a separate signal and sizing logic.
- **(c) Full cash on trigger** — Adopted as the cleanest defensive action for a concentrated sector portfolio: no basis risk, no extra instruments, and clear behavior for operations and reporting.

**Status:** Implemented. Triggers and state are written to `outputs/regime_status.json`; portfolio state (target_weights, regime, weekly_lock) is updated in `outputs/portfolio_state.json`. Emergency liquidations are recorded in the fills ledger for audit.
