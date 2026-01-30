# Dynamic Strategy Selector

The **Dynamic Selector** connects HMM regime detection to strategy execution via a real-time lookup on `data/logs/regime_ledger.csv`. When a regime is detected, the backtest overrides `news_weight` and `sideways_risk_scale` for the upcoming week using the **winning profile** for that regime from the ledger.

---

## Logic Flow

```
  HMM State (BULL / BEAR / SIDEWAYS)
           │
           ▼
  ┌────────────────────────────────┐
  │   Ledger Lookup                │
  │   regime_ledger.csv            │
  │   Last 4 occurrences of regime │
  └────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────┐
  │   Winning Profile              │
  │   Win Rate + Profit Factor     │
  │   per Strategy_ID               │
  │   Tie-break: lowest Max_DD     │
  └────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────┐
  │   Execution Override           │
  │   news_weight, signal_horizon  │
  │   sideways_risk_scale          │
  └────────────────────────────────┘
```

---

## Flow Table

| Step | Component | Action |
| :--- | :--- | :--- |
| 1 | **HMM State** | Regime detected (BULL / BEAR / SIDEWAYS) from `get_regime_hmm(spy_close_native, monday)`. |
| 2 | **Ledger Lookup** | Load `data/logs/regime_ledger.csv`; filter rows where `Regime == current_regime`; keep **last 4 occurrences**. |
| 3 | **Winning Profile** | For each unique `Strategy_ID` in those rows: compute **Win Rate** (fraction of weeks with Return > 0) and **Profit Factor** (gross profits / gross losses). Select the `Strategy_ID` with **highest win rate**; if tied, choose **lowest Max_Drawdown** (least negative). |
| 4 | **Safety** | If ledger has **fewer than 2** occurrences of the regime, or the winning profile has **negative Sharpe**, return no override → use **config defaults** (`config/technical_master_score.yaml`: `news_weight`, and default `sideways_risk_scale` / `signal_horizon_days`). |
| 5 | **Execution Override** | Parse winning `Strategy_ID` (e.g. `nw0.3_h5_r1.0` → news_weight=0.3, horizon=5, risk=1.0). Override **news_weight**, **signal_horizon_days**, **sideways_risk_scale** for the upcoming week. Log: `[SELECTOR] Regime: BEAR detected. Historical Best Profile found: nw0.3_r0.5. Overriding current session weights...` |

---

## Strategy ID Format

- **Full:** `nw{news_weight}_h{horizon}_r{risk}` (e.g. `nw0.3_h5_r1.0`)
- **Short:** `nw{news_weight}_r{risk}` (e.g. `nw0.3_r0.5`) → horizon defaults to 5

Parsed by `parse_strategy_id()` in `src/signals/weight_model.py`; used to set:

- `news_weight` (Technical vs News blend)
- `signal_horizon_days` (1 or 5 for news aggregation)
- `sideways_risk_scale` (0.5 or 1.0 in SIDEWAYS regime)

---

## CLI

- **`--dynamic-selector`**  
  Enables the Dynamic Selector: each Monday, after regime is set, call `StrategySelector.get_winning_profile(regime)` and override weights from the winning profile when available; otherwise use hardcoded defaults from config.

---

## Safety & Fallback

| Condition | Behavior |
| :--- | :--- |
| Ledger has **< 2** occurrences of current regime | No override; use **config defaults** (e.g. `news_weight: 0.20` from `technical_master_score.yaml`, default sideways/horizon). |
| Winning profile has **negative Sharpe** | No override; use **config defaults**. |
| Ledger file missing or unreadable | No override; use **config defaults**. |

This avoids overfitting to thin history and avoids applying a “winning” profile that was loss-making on a risk-adjusted basis.
