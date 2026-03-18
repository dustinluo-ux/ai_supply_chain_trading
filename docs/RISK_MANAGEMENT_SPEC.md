# Risk Management & Circuit-Breakers Specification

**Purpose:** Define the Structural Breakdown Detector, Global Stop-Loss, dashboard enhancements, Telegram alert type, file list, config, and integration. No code—markdown specification only.

**Evidence discipline:** Design decisions that reference existing code cite `filename:line_number`.

---

## Section 1 — Structural Breakdown Detector

### Module and public function

**File:** `src/monitoring/structural_breakdown.py`

**Public function:**

```text
assess_structural_breakdown(
    regime_status: dict,
    prices_dict: dict,
    weights_history: list[dict],   # list of {date, weights} from last_valid_weights history
    ic_history: list[dict],         # from ic_monitor.json or equivalent
    smh_prices: pd.DataFrame,
    config: dict,
) → dict
```

**Return value:** A dict that **extends** the existing `regime_status` schema (see `scripts/regime_monitor.py:116–133`). Do not replace or remove existing keys. Add the following sub-assessments and one overall key.

---

### 1a. IC Decay detector

- **Input:** `ic_history` — list of dicts with at least `date` and `ic` (e.g. from `outputs/ic_monitor.json` as written by `scripts/retrain_model.py:150–166`: `{date, train_end, ic, passed, model_path}`).
- **Compute:** Build a series of IC values ordered by date. Compute the **20-day rolling mean IC** (calendar or rebalance-date alignment as available; if fewer than 20 points, use all available). Compare to **baseline** `ic_baseline` from config (default **0.0428** — source: docs/ENGINEER_ONBOARDING.md CatBoost OOS reference; gate in code is 0.01 in `scripts/retrain_model.py:24`).
- **Trigger:**
  - **WARNING:** rolling mean IC < 0.5 × baseline.
  - **CRITICAL:** rolling mean IC < 0 (model inverting).
- **Output key:** `ic_decay` — dict with:
  - `rolling_ic_20d`: float | None (latest 20d rolling mean, or None if insufficient data)
  - `baseline`: float (from config)
  - `severity`: `"ok"` | `"warning"` | `"critical"`
  - `triggered`: bool

---

### 1b. Residual Risk detector

- **Input:** `weights_history` — list of `{date, weights}` (e.g. from a persisted history of `last_valid_weights.json` snapshots or equivalent). Reconstruct **weekly portfolio P&L** as: for each week, P&L = sum(weight[t] × next_week_return[t]) using `prices_dict` for returns.
- **Compute:**
  - Rolling **8-week P&L volatility** (std of weekly P&L over last 8 weeks).
  - “Explained” fraction: compute Spearman ρ between Master Score rank (or score) at week start and next-week forward returns; define explained fraction as the proportion of P&L variance explained by that rank (e.g. R² from rank vs return, or a specified formula in config). **Baseline 8-week vol** = first 8-week vol in history or a configurable constant.
- **Trigger:**
  - **WARNING:** unexplained P&L vol > 2× baseline 8-week vol (config: `residual_risk_warning_multiple`).
  - **CRITICAL:** unexplained P&L vol > 3× baseline (config: `residual_risk_critical_multiple`).
- **Output key:** `residual_risk` — dict with:
  - `pnl_vol_8w`: float (current 8-week P&L vol)
  - `explained_fraction`: float (0–1)
  - `severity`: `"ok"` | `"warning"` | `"critical"`
  - `triggered`: bool

---

### 1c. Regime Misalignment detector

- **Input:** `prices_dict` + `smh_prices` for realised beta. **Per-pod** portfolio weights are not passed to this function; the spec assumes either (a) pod weights are available from a recent run (e.g. from `outputs/meta_weights.json` and last pod outputs) or (b) the function receives a mapping of pod name → weight Series for the same as_of date. For a minimal design, specify: **realized 20-day portfolio beta to SMH** computed for each pod’s **mandate-implied** portfolio (Core = long-only top N, Extension = 130/30 style, Ballast = defensive/SMH short). If pod weights are not passed, the function may use a single combined portfolio from `weights_history` and compare its beta to the three mandates; or accept optional `pod_weights: dict[str, pd.Series]` and compute beta per pod.
- **Mandates (beta to SMH):**
  - **Core:** beta ∈ [0.8, 1.2] (long-only, near-market).
  - **Extension:** net beta ∈ [-0.2, 0.6] (partial hedge).
  - **Ballast:** beta ∈ [0.0, 0.5] (defensive).
- **Compute:** For each pod, realised 20-day beta = cov(portfolio_returns, smh_returns) / var(smh_returns) over the last 20 trading days. Portfolio returns = sum(weight[t] × return[t]) from `prices_dict` and SMH from `smh_prices`.
- **Trigger:**
  - **WARNING:** any pod’s realised beta outside its mandate ± `beta_mandate_warning_buffer` (default 0.3).
  - **CRITICAL:** any pod’s realised beta outside its mandate ± `beta_mandate_critical_buffer` (default 0.6).
- **Output key:** `regime_misalignment` — dict with:
  - `pod_betas`: dict pod_name → float (realised beta)
  - `mandates`: dict pod_name → [low, high] (mandate range)
  - `severity`: `"ok"` | `"warning"` | `"critical"`
  - `triggered`: bool

---

### Overall severity and write

- **Overall:** `structural_breakdown_severity` = max of the three detectors’ severities (map ok→0, warning→1, critical→2; then take max and map back to `"ok"` | `"warning"` | `"critical"`).
- **Write:** Merge the full `regime_status` (input) with the three sub-dicts and `structural_breakdown_severity` into one output dict, and write it to **`outputs/structural_breakdown.json`**. Include at least: all original `regime_status` keys, plus `ic_decay`, `residual_risk`, `regime_misalignment`, `structural_breakdown_severity`, and a timestamp (e.g. `last_updated`).

---

## Section 2 — Global Stop-Loss

### Interception point in scripts/run_execution.py

The stop-loss is the **outermost gate**: it must be checked **before** any pod computation or weight generation. Today, `account_value` is obtained at **line 459** (`position_manager.get_account_value()`), after the block that computes `optimal_weights_series` (lines 406–442). To satisfy “before any weight generation,” the execution spine must be **restructured** so that:

1. **Executor and PositionManager** are created and **account_value** is obtained **before** the block that computes target weights (i.e. move the block at current lines 444–476 to **before** the block at 406–442). NAV source: `position_manager.get_account_value()` (currently at line 459); after live bridge and fallback from `trading_config.yaml` (lines 462–476).
2. **Immediately after** `account_value` is finalised (and before any call to `_run_pods`, `compute_target_weights`, or rebalance cache read for target weights):
   - Load **`outputs/drawdown_tracker.json`** (create with defaults if missing).
   - **Update tracker:** `peak_nav = max(peak_nav, account_value)`, `current_nav = account_value`, `drawdown = (current_nav - peak_nav) / peak_nav` (if peak_nav <= 0, treat drawdown as 0). Set `last_updated` to current ISO timestamp.
   - If **drawdown ≤ −0.10** (configurable `stop_loss_threshold`): set `flatten_active = True`, log `[STOP-LOSS] Drawdown {drawdown:.1%} hit -10% hard floor — FLATTEN ALL`, fire Telegram alert **`stop_loss`** (see Section 4), write updated tracker to `outputs/drawdown_tracker.json`.
   - If **`flatten_active`** is True (persisted from a previous run): do **not** run pods or pipeline; set `optimal_weights_series = pd.Series(0.0, index=tickers)` and `intent` so that all tickers have weight 0.0; then continue to the rest of the script (PositionManager, delta trades) so that “Flatten All” results in selling to zero. Optionally persist this zero-weight state to `last_valid_weights.json`.
3. **Drawdown tracker schema:** `outputs/drawdown_tracker.json`:
   - `peak_nav`: float  
   - `current_nav`: float  
   - `drawdown`: float (e.g. −0.05 for −5%)  
   - `last_updated`: str (ISO)  
   - `flatten_active`: bool  

**When to write drawdown_tracker.json:** After `account_value` is fetched and updated (peak_nav, current_nav, drawdown), and after any stop-loss trigger (set `flatten_active`), write the file **before** proceeding to weight computation (or to the flatten path).

**Reset:** A new CLI flag **`--reset-stop-loss`** must be supported. When set: after loading the tracker, set `flatten_active = False` and write the tracker, then continue (so the next run can compute weights again). Optionally reset `peak_nav` to `current_nav` so drawdown restarts from today. Exact behaviour (reset peak vs only clear flatten) is implementation choice; spec requires that `--reset-stop-loss` clears the flatten so normal execution resumes.

---

## Section 3 — Dashboard Enhancements

**File:** `scripts/dashboard.py`. Current structure: Panel 1 Regime & Risk (lines 61–84), Panel 2 Portfolio (86–101), Panel 3 Target Weights & Holdings (104–128), Panel 4 Signal Snapshot (130–159), Panel 5 ML Status / IC History (162–199), Panel 6 Fills (201–224). Source: `scripts/dashboard.py` as read.

### 3a. Probabilistic Regime Assignments panel

- **Replace or augment** the current regime display (Panel 1) with a **probability bar**.
- **Source:** Read **`outputs/meta_weights.json`** (written by `scripts/regime_monitor.py` after meta_allocator, see THREE_POD_ARCHITECTURE.md). The three pod weights (`core`, `extension`, `ballast`) serve as the probabilistic regime proxy:
  - **core** weight → **BULL** probability  
  - **extension** weight → **TRANSITION** probability  
  - **ballast** weight → **BEAR** probability  
- **Display:** A **horizontal stacked bar** (Plotly or `st.progress` / Streamlit bar) with three segments: **green** (BULL), **amber** (TRANSITION), **red** (BEAR). Show numeric probability labels (e.g. percentage) on each segment.
- If `meta_weights.json` is missing, show the existing regime display only (from `regime_status.json`) or a message that probabilistic regime is unavailable.

### 3b. Tiered Alert panel

- **Sources:** Read **`outputs/structural_breakdown.json`** and **`outputs/drawdown_tracker.json`**.
- **Render a table** with three tiers:

| Tier            | Colour | Triggers |
|-----------------|--------|----------|
| Informational   | Blue   | IC rolling mean within [0.5×, 1.0×] baseline |
| Warning         | Amber  | IC < 0.5× baseline; residual risk > 2×; beta misalignment > mandate ± 0.3 |
| Critical        | Red    | IC < 0; residual risk > 3×; beta > mandate ± 0.6; drawdown < −10% |

- **Per row:** alert name, current value, threshold, last triggered timestamp (if available from the breakdown or tracker).
- If a file is missing, show a neutral message (e.g. “No alert data”) for that source.

### 3c. Panel ordering

- **New order:**  
  (1) **Probabilistic Regime** (new panel),  
  (2) **Tiered Alerts** (new panel),  
  (3) existing panels in current order: Regime & Risk (if kept separate), Portfolio, Target Weights & Holdings, Signal Snapshot, ML Status / IC History, Fills.

---

## Section 4 — New Telegram Alert Type

**File:** `src/monitoring/telegram_alerts.py`. Existing types: `regime_change`, `rebalance_complete`, `fill_miss`, `ic_degradation`, `thesis_collapse` (see lines 35–93).

- **New alert type:** `stop_loss`
- **Payload:** `{drawdown: float, peak_nav: float, current_nav: float}`
- **Message format (Markdown):**  
  `🚨 STOP-LOSS TRIGGERED — Portfolio drawdown {drawdown:.1%} hit -10% floor. FLATTEN ALL initiated.`

Add a new `elif alert_type == "stop_loss":` branch (e.g. after `thesis_collapse`), format the message from the payload, and send via the same `sendMessage` path as other types.

---

## Section 5 — New File List & Integration Points

### New files

| File | Purpose |
|------|---------|
| `src/monitoring/structural_breakdown.py` | Implements `assess_structural_breakdown()`; IC decay, residual risk, regime misalignment; writes `outputs/structural_breakdown.json`. |
| `outputs/drawdown_tracker.json` | Created/updated by the drawdown module used in run_execution; schema in Section 2. |
| `outputs/structural_breakdown.json` | Written by `assess_structural_breakdown()`; extends regime_status with breakdown keys. |

(No separate “drawdown module” file is mandated; the logic may live in `run_execution.py` or a small helper in `src/monitoring/` that updates/reads the tracker.)

### Modified files

| File | Purpose |
|------|---------|
| `scripts/regime_monitor.py` | After writing `outputs/meta_weights.json`, call `assess_structural_breakdown()` (with regime_status, prices_dict, weights_history, ic_history, smh_prices, config), then write or merge result to `outputs/structural_breakdown.json`. |
| `scripts/run_execution.py` | Restructure so NAV is fetched before weight computation; add drawdown load/update and stop-loss check as outermost gate; add `--reset-stop-loss`; when flatten_active or drawdown ≤ threshold, set zero weights and skip pods/pipeline. |
| `scripts/dashboard.py` | Add Probabilistic Regime panel (meta_weights.json), Tiered Alert panel (structural_breakdown.json, drawdown_tracker.json); reorder panels per 3c. |
| `src/monitoring/telegram_alerts.py` | Add `stop_loss` alert type and message format. |
| `config/model_config.yaml` | Add `risk_management:` block per Section 6. |

### Integration sequence

1. **regime_monitor.py** — After writing `regime_status.json` and (if present) `meta_weights.json`, call `assess_structural_breakdown()` with inputs from config, `outputs/ic_monitor.json`, and a weights history source (e.g. last_valid_weights or a dedicated history file). Write `outputs/structural_breakdown.json`.
2. **run_execution.py** — Before any pod or pipeline weight computation: create executor and position_manager, get account_value, then load/update drawdown_tracker; if drawdown ≤ −0.10 or flatten_active, set flatten_all weights, log, send stop_loss alert, write tracker, and skip weight generation; else run existing rebalance/pods/pipeline path. Support `--reset-stop-loss` to clear flatten_active.
3. **dashboard.py** — Read `structural_breakdown.json` and `drawdown_tracker.json` in addition to existing sources; add Probabilistic Regime and Tiered Alert panels; order panels as (1) Probabilistic Regime, (2) Tiered Alerts, (3) existing panels.

---

## Section 6 — Config Additions

Add to **`config/model_config.yaml`** a new top-level key **`risk_management:`** with:

```yaml
risk_management:
  ic_baseline: 0.0428
  ic_decay_window: 20
  stop_loss_threshold: -0.10
  residual_risk_warning_multiple: 2.0
  residual_risk_critical_multiple: 3.0
  beta_mandate_warning_buffer: 0.3
  beta_mandate_critical_buffer: 0.6
```

- `ic_baseline`: baseline IC for decay detector (0.0428 = OOS reference; gate in retrain_model.py is 0.01).
- `ic_decay_window`: number of periods for rolling mean IC (20).
- `stop_loss_threshold`: drawdown level that triggers flatten (e.g. −0.10).
- `residual_risk_warning_multiple` / `residual_risk_critical_multiple`: multiples of baseline 8-week P&L vol for warning/critical.
- `beta_mandate_warning_buffer` / `beta_mandate_critical_buffer`: tolerance outside mandate for warning/critical.

---

## Reconciliation Items

- **NAV / line number:** The spec refers to “line ~299” for `position_manager.get_account_value()`. In the current **scripts/run_execution.py**, `account_value` is set at **line 459**, and the weight computation block is at **406–442**. So the Global Stop-Loss requires **restructuring**: move executor/position_manager/account_value **before** the rebalance/pods block so the stop-loss can run before any weight generation.
- **IC baseline vs gate:** **scripts/retrain_model.py:24** uses **IC_GATE = 0.01** for model save/update. The spec uses **ic_baseline = 0.0428** as the decay detector baseline (reference OOS IC from docs/ENGINEER_ONBOARDING.md). So: gate remains 0.01 in code; risk_management.ic_baseline is 0.0428 for the structural breakdown detector only.
- **IC history path:** The spec and dashboard refer to **outputs/ic_monitor.json**; **scripts/retrain_model.py:25** uses **ROOT / "outputs" / "ic_monitor.json"**. Same file. **scripts/dashboard.py:175** loads `outputs/ic_monitor.json`; format is a list of `{date, train_end, ic, passed, model_path}`. Structural breakdown uses this as `ic_history`.
- **Weights history:** `weights_history` for residual risk is a list of `{date, weights}`. Currently only **last_valid_weights.json** (single snapshot) is written by run_execution. The Engineer must define how to build or persist a history (e.g. append-only file, or use last_valid_weights as a single-point history until a dedicated history is implemented).
- **Regime misalignment pod weights:** Per-pod betas require per-pod portfolio weights at the same date. The spec leaves open whether `assess_structural_breakdown` receives optional `pod_weights: dict[str, pd.Series]` or derives a single portfolio from `weights_history` and compares one beta to the three mandates. Reconcile in implementation: either pass pod weights from the last run or use aggregated weights and one beta vs mandates.
- **regime_status schema extension:** The detector returns a dict that extends regime_status with the new keys. That merged dict is written to **outputs/structural_breakdown.json** only; **outputs/regime_status.json** is not overwritten by the breakdown detector. So regime_status.json schema stays unchanged; structural_breakdown.json holds the extended view for dashboard and alerts.
- **--pods path:** When stop-loss triggers (flatten_active or drawdown ≤ threshold), both the `--pods` path and the non-pods (compute_target_weights) path are skipped; execution uses the zero-weight flatten path only.

---

**End of specification.**
