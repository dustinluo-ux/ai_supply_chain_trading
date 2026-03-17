# Three-Pod Architecture Specification

**Purpose:** Define the Pod interfaces, Bayesian Meta-Allocator, aggregator, integration points, file list, and config for the three-pod system. No code—markdown specification only. Implement from this doc.

**Evidence discipline:** Design decisions that reference existing code cite `filename:line_number`.

---

## Section 1 — Pod Interfaces

### Common abstract interface

All three pods implement the same call signature:

```text
Pod.generate_weights(
    scores: pd.Series,           # ticker → master_score [0, 1]
    prices_dict: dict,            # ticker → OHLCV DataFrame
    regime_status: dict,          # from outputs/regime_status.json
    config: dict,                 # pod-specific config block
) → pd.Series                    # ticker → weight (negative = short)
```

- **scores:** Same scale as Master Score from `src/signals/technical_library.py` (e.g. output of `compute_signal_strength`, or blended score from target_weight_pipeline). Index = ticker, values in [0, 1].
- **prices_dict:** Same structure as used in `src/core/target_weight_pipeline.py` and `scripts/run_execution.py:57` — ticker → DataFrame with at least `close` (and optionally `open`, `high`, `low`, `volume`).
- **regime_status:** Structure written by `scripts/regime_monitor.py:116–133` — at least `regime`, `vix`, `spy_below_sma`, `score_floor`; may include `vix_z` if added later.
- **config:** Pod-specific dict (e.g. from `config/model_config.yaml` under `tracks.D` or a dedicated `pods` block).
- **Return:** `pd.Series` indexed by ticker; positive = long, negative = short; sum of weights = net exposure (typically ~1.0 before meta blend). Tickers not in the pod’s universe may be omitted or present with 0.0.

Scores are assumed to be produced by the existing pipeline (e.g. SignalEngine + `technical_library.compute_signal_strength` or `apply_ml_blend` output). Pods do not compute Master Score; they consume a single `scores` Series per run.

### Pod locations and what each wraps

| Pod | File | Wraps | Max gross | Notes |
|-----|------|--------|-----------|--------|
| **Core** | `pods/pod_core.py` | Existing HRP + Alpha Tilt (long-only). Source: long-side logic from `src/portfolio/long_short_optimizer.py:build_long_short_weights` (HRP on top N, `scripts/portfolio_optimizer.py:218–256` HRP + alpha tilt pattern). ATR-based sizing from `src/portfolio/position_sizer.py` (e.g. `compute_weights`, `compute_atr_series`) can be used for risk scaling. | 1.0× | Long-only. No shorts. Weights sum to 1.0. Master Score / pipeline scores drive ranking; HRP allocates among top N. |
| **Extension** | `pods/pod_extension.py` | `rebalance_alpha_sleeve` from `src/portfolio/long_short_optimizer.py:366–417`. | 1.6× | Uses `config/model_config.yaml` `tracks.D` (top_n, bottom_n, target_vol, max_leverage, max_position, dispersion_anchor, etc.). Dynamic short sleeve S ∈ [0, 0.30]; long book L = 1.0 base; multiplier ceiling shared when S > 0. |
| **Ballast** | `pods/pod_ballast.py` | SMH hedge logic from `src/core/hedger.py` (Hedger, `rolling_ols_beta`, hedge ratio / borrow cost). Adds cash and defensive allocation when regime = BEAR. | 1.0× | When regime ≠ BEAR: long-only defensive or minimal exposure per spec. When regime = BEAR: 50% cash, 30% defensive longs (lowest-vol tickers from universe), 20% SMH short. Produces a **weight vector** (cash as 0.50, tickers + SMH); hedger’s return-level API is used conceptually to size SMH short (e.g. beta-based notionals). |

**Pod Core detail:** Build long-only weights from scores: (1) select top N by score (N from config, e.g. same as Track D `top_n` or a core-specific cap); (2) build returns from `prices_dict` (e.g. 60d lookback); (3) run HRP on that universe (same pattern as `long_short_optimizer.py:134–158` and `scripts/portfolio_optimizer.py:240–243`); (4) normalise so sum = 1.0. Optionally apply ATR-based scaling from `position_sizer.compute_weights` for target_exposure. No short positions; max gross = 1.0.

**Pod Ballast detail:** `src/core/hedger.py` exposes `apply_hedge(portfolio_returns, smh_returns, portfolio_beta)` → `HedgeResult` (returns and metrics), not a weight vector. Pod Ballast therefore (1) derives a **weight** allocation: BEAR → 50% cash, 30% defensive longs, 20% SMH short; (2) uses Hedger-style logic (e.g. `rolling_ols_beta`, hedge_ratio) only to size the SMH short notional or to compute metrics for fitness; (3) returns a `pd.Series` that includes a sentinel or explicit cash weight and SMH (e.g. one row for "SMH" with negative weight). Defensive longs = lowest realised-vol tickers from the universe (e.g. 20d ann. vol from `prices_dict`), equal-weight or vol-inverse within the 30%.

---

## Section 2 — Bayesian Meta-Allocator

### Module and function

**File:** `pods/meta_allocator.py`

**Public function:**

```text
compute_pod_weights(
    pod_fitness: dict,       # {"core": {"sharpe": x, "mdd": y}, "extension": ..., "ballast": ...}
    regime_status: dict,
    prior: dict | None,      # optional Dirichlet prior; default {"core": 0.50, "extension": 0.30, "ballast": 0.20}
    temperature: float,       # softmax temperature; default 0.5
    ballast_floor: float,   # minimum ballast weight; default 0.20
) → dict                     # {"core": w1, "extension": w2, "ballast": w3}, sum = 1.0
```

### Algorithm

1. **Fitness score per pod:** `F[pod] = sharpe / (1 + abs(mdd))`. If a pod has no history or missing sharpe/mdd, treat F[pod] = 0.
2. **Likelihood:** `L[pod] = exp(F[pod] / temperature)`.
3. **Posterior (unnormalised):** `w_raw[pod] = prior[pod] × L[pod]`. Use `prior` from argument; if `prior is None`, use default `{"core": 0.50, "extension": 0.30, "ballast": 0.20}`.
4. **Normalise:** `w[pod] = w_raw[pod] / sum(w_raw.values())`.
5. **Ballast floor:** `w["ballast"] = max(ballast_floor, w["ballast"])`.
6. **Renormalise core + extension:** Scale only `w["core"]` and `w["extension"]` so that `w["core"] + w["extension"] = 1.0 - w["ballast"]` (preserve their relative ratio).
7. Return `{"core": w_core, "extension": w_ext, "ballast": w_ballast}` with sum = 1.0.

### Fitness persistence

- **Path:** `outputs/pod_fitness.json` (overridable via config `pods.fitness_path`).
- **Structure:**

```json
{
  "core":      { "sharpe": 0.526, "mdd": -0.094, "updated": "2026-03-17" },
  "extension": { "sharpe": 0.206, "mdd": -0.233, "updated": "2026-03-17" },
  "ballast":   { "sharpe": 0.10,  "mdd": -0.050, "updated": "2026-03-17" }
}
```

- **Read:** If the file exists, load it and use `core`, `extension`, `ballast` for `pod_fitness` (with keys `sharpe`, `mdd`; `updated` optional).
- **Write:** After backtest or live evaluation, update the file with latest sharpe and mdd per pod (and `updated` timestamp).
- **Bootstrap:** If the file is absent, bootstrap from existing backtest baselines (e.g. 2024 OOS). Use placeholder values so that `compute_pod_weights` still runs (e.g. core 0.5 sharpe, -0.10 mdd; extension 0.2, -0.20; ballast 0.1, -0.05). Document source of bootstrap in code comments or config.

---

## Section 3 — Conflict Resolution / Aggregation

### Module and function

**File:** `pods/aggregator.py`

**Public function:**

```text
aggregate_pod_weights(
    pod_weights: dict[str, pd.Series],   # {"core": Series, "extension": Series, "ballast": Series}
    meta_weights: dict[str, float],      # from compute_pod_weights()
    universe_pillars: dict[str, list],   # from universe.yaml pillars (pillar name → list of tickers)
    sector_cap: float,                   # max weight per pillar; default 0.40
    gross_cap: float,                    # max gross exposure; default 1.6
) → pd.Series                            # final ticker → weight
```

### Algorithm

1. **Weighted sum:** For each ticker `t`, `raw[t] = Σ meta_weights[pod] × pod_weights[pod].get(t, 0.0)` (sum over pods). If a pod’s Series does not index `t`, use 0.0.
2. **Sector cap:** For each pillar in `universe_pillars`, let `pillar_tickers` = that pillar’s list. If `Σ abs(raw[t] for t in pillar_tickers) > sector_cap`, scale down all `raw[t]` for `t in pillar_tickers` proportionally so the pillar’s total absolute weight = `sector_cap`.
3. **Gross cap:** Let `gross = Σ abs(raw[t])` over all t. If `gross > gross_cap`, multiply every `raw[t]` by `gross_cap / gross`.
4. **Net sanity check:** Let `net = Σ raw[t]`. If `net` is outside [0.85, 1.15], log a WARNING (do not crash). Return the resulting `pd.Series` (ticker → weight).

**Universe:** The union of all tickers appearing in any `pod_weights[pod]` (and optionally the full universe from config) defines the index of the returned Series; missing tickers get 0.0.

---

## Section 4 — Integration Points

### scripts/regime_monitor.py

- **Current behaviour:** Writes `outputs/regime_status.json` (see `scripts/regime_monitor.py:133–137`). No pod or meta-allocator call.
- **Change:** After writing `regime_status.json`, call `compute_pod_weights(pod_fitness, regime_status, prior=..., temperature=..., ballast_floor=...)` where `pod_fitness` is read from `outputs/pod_fitness.json` (or bootstrapped). Write the returned dict to `outputs/meta_weights.json`. Paths for fitness and meta_weights come from config (`pods.fitness_path`, `pods.meta_weights_path`). Do not change the existing regime_status write logic (VIX, SPY 200-SMA, SMH, score_floor).

### scripts/run_execution.py

- **Current behaviour:** When not in `--rebalance` mode, target weights come from a single call to `compute_target_weights(...)` (see `scripts/run_execution.py:263–272`), which delegates to `src.core.target_weight_pipeline.compute_target_weights` (see `scripts/run_execution.py:127`). The result is `optimal_weights_series`; intent is built at 274; `PositionManager.calculate_delta_trades(current_weights, optimal_weights=optimal_weights_series, ...)` at 324–331.
- **Change:** Replace the single pipeline call with: (1) Run all three pods: call `pod_core.generate_weights(scores, prices_dict, regime_status, config_core)`, `pod_extension.generate_weights(...)`, `pod_ballast.generate_weights(...)` with a common `scores` and `prices_dict`. Scores must be the same Master Score (or pipeline output) used for the run; regime_status from `outputs/regime_status.json` (load if present); config per pod from `model_config.yaml` / pods config. (2) Call `aggregate_pod_weights(pod_weights, meta_weights, universe_pillars, sector_cap, gross_cap)`. (3) Pass the returned Series as `optimal_weights_series` into the rest of the flow (intent, PositionManager, delta trades, SMH hedge row if still applicable). When `--rebalance` is used, keep using cached weights from `last_valid_weights.json` as today; the three-pod path applies to the non-rebalance (full signal) run. Optionally: persist the aggregated weights to `last_valid_weights.json` after a successful run so that the next `--rebalance` uses the same allocation.

---

## Section 5 — New File List

### New files to create

| File | Purpose |
|------|---------|
| `pods/__init__.py` | Package init; optionally export `compute_pod_weights`, `aggregate_pod_weights`, pod classes. |
| `pods/pod_core.py` | Pod Core: implements `generate_weights`; long-only HRP + Alpha Tilt; max gross 1.0. |
| `pods/pod_extension.py` | Pod Extension: implements `generate_weights`; wraps `rebalance_alpha_sleeve` from `src/portfolio/long_short_optimizer.py`; config from tracks.D. |
| `pods/pod_ballast.py` | Pod Ballast: implements `generate_weights`; BEAR → 50% cash, 30% defensive longs, 20% SMH short; uses SMH hedge logic from `src/core/hedger.py`. |
| `pods/meta_allocator.py` | Bayesian meta-allocator: `compute_pod_weights(pod_fitness, regime_status, prior, temperature, ballast_floor)`; read/write `pod_fitness.json`. |
| `pods/aggregator.py` | `aggregate_pod_weights(pod_weights, meta_weights, universe_pillars, sector_cap, gross_cap)` → final Series. |

### Existing files to modify

| File | Change |
|------|--------|
| `scripts/regime_monitor.py` | After writing `regime_status.json`, call `compute_pod_weights`, write `outputs/meta_weights.json`. |
| `scripts/run_execution.py` | Replace single `compute_target_weights` call (non-rebalance path) with: run three pods → `aggregate_pod_weights` → use result as `optimal_weights_series`. Load regime_status and meta_weights from outputs. |
| `config/model_config.yaml` | Add `pods` block per Section 6. |

---

## Section 6 — Config Block

Add the following to `config/model_config.yaml` (new top-level key `pods`):

```yaml
pods:
  meta_allocator:
    temperature: 0.5
    ballast_floor: 0.20
    prior:
      core: 0.50
      extension: 0.30
      ballast: 0.20
  sector_cap: 0.40
  gross_cap: 1.60
  fitness_path: outputs/pod_fitness.json
  meta_weights_path: outputs/meta_weights.json
```

- `meta_allocator.temperature`, `ballast_floor`, `prior` are passed through to `compute_pod_weights` when invoked from regime_monitor or run_execution.
- `sector_cap` and `gross_cap` are used in `aggregate_pod_weights`.
- `fitness_path` and `meta_weights_path` are used for reading/writing pod fitness and meta weights.

Existing `tracks.D` (e.g. `top_n`, `bottom_n`, `target_vol`, `max_leverage`, `max_position`, `dispersion_anchor`) remains the Extension pod config source.

---

## Reconciliation Items

- **Hedger location:** The task refers to `src/portfolio/hedger.py`. The actual module is **`src/core/hedger.py`** (see `src/core/hedger.py:1`). Pod Ballast should import and use `src.core.hedger` (e.g. `Hedger`, `rolling_ols_beta`) for SMH hedge logic; the pod itself produces a **weight** vector (cash + defensive longs + SMH short), not a return series.
- **Hedger interface:** `Hedger.apply_hedge(portfolio_returns, smh_returns, portfolio_beta)` returns `HedgeResult` (hedged_returns, sharpe, total_return, max_drawdown, n_periods, portfolio_beta_used). It does not have `generate_weights(scores, prices_dict, regime_status, config)`. Pod Ballast must implement `generate_weights` by (1) deciding regime from `regime_status`; (2) in BEAR, building weights 50% cash, 30% defensive longs, 20% SMH short; (3) using Hedger only for beta/notional or fitness metrics, and returning a pd.Series of weights (including a negative weight for SMH if applicable).
- **Pod Extension entry point:** The task names `rebalance_alpha_sleeve` as the Pod Extension entry point. That function exists in **`src/portfolio/long_short_optimizer.py:366–417`**. It takes `(scores, scores_df, prices_dict, regime_status, config)` and returns `pd.Series`. The common pod interface uses `(scores, prices_dict, regime_status, config)`; Extension must obtain or mock `scores_df` (e.g. from a persisted history or empty DataFrame if unavailable) when calling `rebalance_alpha_sleeve`, or the interface may be extended to pass `scores_df` optionally.
- **regime_status keys:** `scripts/regime_monitor.py` writes `regime` ("NORMAL" | "EMERGENCY"), not "BEAR". For Pod Ballast, "BEAR" can be inferred from `spy_below_sma === true` (or a dedicated key if added). Spec: when `regime_status` indicates bearish (e.g. `spy_below_sma` true or `regime == "EMERGENCY"`), apply the 50/30/20 ballast allocation; otherwise Ballast may return minimal or defensive long-only weights so that meta_allocator can still blend it.

---

**End of specification.**
