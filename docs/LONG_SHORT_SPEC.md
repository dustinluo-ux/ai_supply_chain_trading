# Track D — 130/30 Long/Short with Volatility Throttle + Thesis Monitor

**Spec for:** `src/portfolio/long_short_optimizer.py`  
**Deliverable:** Numbered specification only. No code. No file edits beyond this document.  
**Evidence discipline:** Every design decision that references existing code cites `filename:line_number`.

---

## 1. Evidence read (file:line citations)

### Pre-check
- **src/signals/technical_library.py:17–19** — NumPy NaN compatibility patch is present immediately before the pandas_ta import block (`import numpy as _np`; `if not hasattr(_np, 'NaN'): _np.NaN = _np.nan`). No modification required.

### Target weight pipeline and ML blend
- **src/core/target_weight_pipeline.py:89–174** — `apply_ml_blend(week_scores, as_of, prices_dict, news_signals, ...)` returns `dict[str, float]` (ticker → blended score). Used as the “Final Score” input for long/short ranking.
- **src/core/target_weight_pipeline.py:202–335** — `compute_target_weights` builds the spine (SignalEngine → PolicyEngine → PortfolioEngine); `scores_to_use` / `week_scores` are the score sources; output is `pd.Series` of weights indexed by ticker.
- **src/core/target_weight_pipeline.py:354** — `portfolio_context = {"top_n": top_n, "atr_norms": atr_norms, "tickers": tickers}`; `top_n` is the selection size for the long book in the current pipeline.

### HRP and alpha tilt
- **scripts/portfolio_optimizer.py:218–256** — Eligible tickers; `returns_dict` built from price DataFrames (60-day lookback, `min_obs=30`); `returns_df = pd.concat(returns_dict, axis=1, join="outer")`; HRP via `HRPOpt(returns=returns_df)`, `hrp.optimize(linkage_method="ward")`; `hrp_result.to_dict()` or `dict(hrp_result)` for weights.
- **scripts/portfolio_optimizer.py:266–277** — HRP base weights plus alpha tilt: `tilted_w = {t: hrp_base_weight[t] * (scores[t] / mean_score) for t in eligible}`, then renormalise. Long-side allocation in the new module must use this same HRP methodology (call or replicate the same pattern).

### Hedger (short implementation pattern)
- **src/core/hedger.py:88–137** — `apply_hedge` takes `portfolio_returns`, `smh_returns`, optional `portfolio_beta`; applies linear hedge with per-period borrow cost. Pattern: external returns + same-length hedge returns; no in-file “short weight vector” but demonstrates the borrow/hedge structure. Track D short book is separate (negative weights on bottom_n tickers).

### Regime status (output structure)
- **outputs/regime_status.json** — Not in repo (generated at runtime). Structure is defined by **scripts/regime_monitor.py:116–133**: `as_of`, `regime`, `reasons`, `score_floor`, `vix`, `spy_close`, `spy_sma200`, `spy_below_sma`, `smh_daily_return`, `smh_shock`, `thresholds`. **Note:** `vix_z` is computed in regime_monitor (lines 79–84) but **not** currently written to the JSON. Spec therefore requires: read `vix_z` from `regime_status` if present; else compute from VIX using 20-day rolling mean/std (see Function 4).

### Config (tracks and score)
- **config/model_config.yaml:46–49** — `tracks.A` and `tracks.B` only; each has `model_path`. No `tracks.C` or `tracks.D` yet.
- **config/technical_master_score.yaml** — Category weights (e.g. trend 0.4, momentum 0.3, volume 0.2, volatility 0.1); Master Score is normalised (e.g. 0–1 via sub-scores). Final Score used for long/short is the output of `apply_ml_blend` (or policy-gated score from the pipeline).

### Telegram alerts
- **src/monitoring/telegram_alerts.py:24–82** — `send_alert(alert_type: str, payload: dict)`. Supported `alert_type`: `regime_change`, `rebalance_complete`, `fill_miss`, `ic_degradation`. Unknown types are skipped with a stderr message. New type `thesis_collapse` to be added per §4.

---

## 2. Function specs (src/portfolio/long_short_optimizer.py)

### Function 1: `get_leverage_multiplier`

**Signature:**  
`get_leverage_multiplier(target_vol: float, portfolio_returns: pd.Series, vix_z: float, max_leverage: float) -> float`

**Purpose:**  
Returns a leverage scaler in `[0.0, max_leverage]` based on realised portfolio volatility and VIX stress level.

**Parameters:**
- `target_vol`: float — target annualised volatility (e.g. 0.15).
- `portfolio_returns`: pd.Series — daily portfolio returns (index = date or integer; values = period return).
- `vix_z`: float — VIX z-score (e.g. from regime_status or computed from 20d VIX).
- `max_leverage`: float — maximum leverage cap (e.g. 1.6).

**Logic:**
1. If `len(portfolio_returns) < 10`: return `1.0` (insufficient data; no scaling).
2. **Emergency floor:** If `vix_z > 2.0`: return `0.1` regardless of vol calculation.
3. Compute 20-day annualised realised volatility: use the last 20 observations of `portfolio_returns`, then `realised_vol = portfolio_returns.tail(20).std() * sqrt(252)` (or equivalent; 252 = annualisation factor for daily returns).
4. Base multiplier: `raw = min(target_vol / realised_vol, max_leverage)`. If `realised_vol <= 0`, treat as infinite vol and set multiplier to `0.0` (or clip to 0).
5. Clip `raw` to `[0.0, max_leverage]`.
6. Return the resulting float.

**Edge cases:**
- Fewer than 10 observations → return `1.0`.
- `vix_z > 2.0` → return `0.1`.
- Empty or all-NaN series after dropna → treat as insufficient data → return `1.0` (or 0.0 per implementer choice for “no exposure”; spec says 1.0 for “no scaling” when insufficient data).

**Return type:** `float`.

---

### Function 2: `check_thesis_integrity`

**Signature:**  
`check_thesis_integrity(scores_df: pd.DataFrame, top_n: int, bottom_n: int, window: int = 60) -> dict`

**Purpose:**  
Detects whether the long basket and short basket are becoming correlated (long/short edge collapsing). Both baskets are from the same 40-stock AI/semiconductor universe: long = top `top_n` by score, short = bottom `bottom_n` by score.

**Parameters:**
- `scores_df`: pd.DataFrame — index = date (or datetime); columns = tickers; values = daily Final Score (same scale as output of `apply_ml_blend` in target_weight_pipeline.py).
- `top_n`: int — number of long candidates (top by score).
- `bottom_n`: int — number of short candidates (bottom by score).
- `window`: int — number of trading days to consider (default 60).

**Logic:**
1. Restrict to the last `window` trading days of `scores_df` (e.g. `scores_df.tail(window)`).
2. If the resulting length is fewer than 30 observations: return `{"rho": None, "thesis_alert": False, "alert_reason": "insufficient data"}`.
3. For each date in this window:  
   - Long basket = top `top_n` tickers by score that day (descending).  
   - Short basket = bottom `bottom_n` tickers by score that day (ascending).
4. Compute two series over the window:  
   - **L**: for each date, mean of the scores of the long-basket tickers that day.  
   - **S**: for each date, mean of the scores of the short-basket tickers that day.
5. Compute rolling 60-day Pearson correlation ρ between L and S. Use the **last** value of this rolling correlation (i.e. most recent 60-day ρ). If the rolling window is 60 and we have exactly 60 dates, that is one correlation value; if more than 60, use the correlation over the full window or the last 60 days — spec: “rolling 60-day Pearson correlation” then “ρ” as the value to report; define as the correlation of L and S over the (up to) last 60 days available in the slice.
6. `thesis_alert = True` if `ρ > 0.8`.
7. `alert_reason`: string explaining the alert (e.g. "correlation above 0.8" when `thesis_alert` is True, or "insufficient data" when applicable).
8. Return `{"rho": <float or None>, "thesis_alert": bool, "alert_reason": str}`.

**Edge cases:**
- Fewer than 30 observations in the window → return `{"rho": None, "thesis_alert": False, "alert_reason": "insufficient data"}`.
- If `scores_df` has missing values, define behaviour (e.g. dropna for that day or fill with neutral 0.5); spec leaves exact handling to implementer but requires a deterministic result.

**Return type:** `dict` with keys `rho`, `thesis_alert`, `alert_reason`.

---

### Function 3: `build_long_short_weights`

**Signature:**  
`build_long_short_weights(scores: pd.Series, prices_dict: dict, top_n: int, bottom_n: int, multiplier: float, thesis_alert: bool, max_position: float = 0.05) -> pd.Series`

**Purpose:**  
Builds the 130/30 weight vector with vol throttle and thesis-alert adjustments. Uses existing HRP logic for the long side (as in scripts/portfolio_optimizer.py); equal-weight short side; applies `multiplier`, thesis reduction, and max-position cap.

**Parameters:**
- `scores`: pd.Series — current Final Scores per ticker (index = ticker); same as output of `apply_ml_blend` / pipeline scores for the universe.
- `prices_dict`: dict — ticker → DataFrame with at least `close` (and optionally `volume`) for returns/correlation; same structure as in target_weight_pipeline and portfolio_optimizer.
- `top_n`: int — number of long positions.
- `bottom_n`: int — number of short positions.
- `multiplier`: float — from `get_leverage_multiplier`; applied to all non-cash weights.
- `thesis_alert`: bool — if True, reduce gross exposure by 50% (long ×0.65, short ×0.15).
- `max_position`: float — max absolute weight per ticker (default 0.05).

**Logic:**
1. **Long candidates:** top `top_n` tickers by `scores` (descending). **Short candidates:** bottom `bottom_n` tickers by `scores` (ascending). All from the same universe (no separate sector lists).
2. **Base 130/30:** Long side sums to +1.30, short side sums to -0.30, net +1.0.
3. **Long-side allocation:** Use existing HRP logic from scripts/portfolio_optimizer.py (lines 218–243): build `returns_dict` for long candidates from `prices_dict` (e.g. 60-day lookback, min_obs=30), form `returns_df`, call `HRPOpt(returns=returns_df).optimize(linkage_method="ward")`, obtain weights; normalise so long weights sum to 1.0, then scale to 1.30. If HRP fails or insufficient data, use equal weight across long candidates and scale to 1.30.
4. **Short-side allocation:** Equal weight across the `bottom_n` tickers; each short weight = -0.30 / bottom_n.
5. **Thesis alert:** If `thesis_alert` is True: multiply long weights by 0.65 (long sum → 0.65×1.30 = 0.845), short weights by 0.15 (short sum → 0.15×(-0.30) = -0.045). Net risky = 0.80. Set cash weight = 1 - sum(weights) so total portfolio net = 1.0. “redistribute freed short allocation to cash” means the portfolio is less than 100% invested; do not add negative weights elsewhere. Optionally scale so net stays ~1.0 (e.g. add cash weight 0.20) — spec says “reduce longs proportionally so net stays ~1.0” only in the sense of not creating new shorts; net can be 0.80 + 0.20 cash = 1.0.
6. **Apply multiplier:** Multiply all non-cash (long and short) weights by `multiplier`. Cash is not multiplied.
7. **Max position:** Enforce `|weight| <= max_position` per ticker; clip and redistribute excess proportionally (only among the side that was clipped, or as specified) so that long sum and short sum remain consistent.
8. **Sanity check 1:** `sum(abs(weights)) <= 1.6 * multiplier`. If violated, scale all non-cash weights down proportionally until `sum(abs(weights)) == 1.6 * multiplier` (or just below).
9. **Sanity check 2:** `sum(weights)` must be in [0.9, 1.1]. If outside, log a warning; do not crash.
10. Return a `pd.Series` indexed by ticker; positive = long, negative = short. Include only tickers with non-zero weight (or include all universe tickers with 0.0 for others — spec “indexed by ticker” suggests at least all long + short tickers; zeros for others is acceptable).

**Edge cases:**
- Fewer than 2 long candidates with sufficient return history for HRP → equal weight long.
- Empty `scores` or no valid tickers → return empty Series or all-zero Series as appropriate.
- `multiplier == 0` → all non-cash weights become 0 (cash 1.0).

**Return type:** `pd.Series` (index = ticker; values = weight).

---

### Function 4: `rebalance_long_short`

**Signature:**  
`rebalance_long_short(scores: pd.Series, scores_df: pd.DataFrame, prices_dict: dict, regime_status: dict, config: dict) -> pd.Series`

**Purpose:**  
Orchestrator: calls get_leverage_multiplier → check_thesis_integrity → build_long_short_weights and returns the final weight vector. Sends a Telegram alert when thesis_alert is True.

**Parameters:**
- `scores`: pd.Series — current Final Scores per ticker (as for Function 3).
- `scores_df`: pd.DataFrame — historical daily scores (index = date, columns = tickers) for thesis check.
- `prices_dict`: dict — ticker → OHLCV DataFrame.
- `regime_status`: dict — from outputs/regime_status.json (see regime_monitor.py:116–133). Must support at least `vix`; `vix_z` optional.
- `config`: dict — Track D config: `target_vol`, `max_leverage`, `top_n`, `bottom_n`, `max_position` (and optionally `thesis_alert_rho`, `borrow_cost_threshold` for future use).

**Logic:**
1. Read from `config`: `target_vol`, `max_leverage`, `top_n`, `bottom_n`, `max_position`. Use defaults if keys missing (e.g. target_vol=0.15, max_leverage=1.6, top_n=15, bottom_n=8, max_position=0.05).
2. **Portfolio returns for multiplier:** If prior weights are available (e.g. from a persisted state or passed in config), compute portfolio_returns as the daily returns of a portfolio using those weights and `prices_dict`. If no prior weights: compute portfolio_returns as equal-weight across current long candidates (top `top_n` by `scores`) using `prices_dict` (daily returns, then EW portfolio return series). Result: `portfolio_returns` = pd.Series of daily returns.
3. **vix_z:** If `regime_status` has key `"vix_z"` and value is numeric, use it. Else: compute from `regime_status["vix"]` using 20-day rolling mean and std of VIX. Fallback: if no VIX history is available in regime_status, fetch 20-day VIX history from the same source as regime_monitor (e.g. yfinance ^VIX), compute mean and std, then `vix_z = (vix - mean) / std`; if still not possible (e.g. no vix), set `vix_z = 0.0`.
4. Call `multiplier = get_leverage_multiplier(target_vol, portfolio_returns, vix_z, max_leverage)`.
5. Call `thesis_result = check_thesis_integrity(scores_df, top_n, bottom_n)` (use default window=60).
6. If `thesis_result["thesis_alert"]` is True: call `send_alert("thesis_collapse", {"rho": thesis_result["rho"], "reason": thesis_result["alert_reason"]})`. Import `send_alert` locally (e.g. inside the function or at top of block that uses it), not at top level of the module, to avoid circular or heavy dependencies at load time.
7. Call `weights = build_long_short_weights(scores, prices_dict, top_n, bottom_n, multiplier, thesis_result["thesis_alert"], max_position)`.
8. Return `weights`.

**Return type:** `pd.Series` (ticker → weight).

---

## 3. Config additions (Engineer adds to config/model_config.yaml)

Add under `tracks:` (same level as `A` and `B`):

```yaml
  D:
    mode: long_short_130_30
    top_n: 15
    bottom_n: 8
    target_vol: 0.15
    max_leverage: 1.6
    max_position: 0.10  # 10% per position — 5% incompatible with 130/30 at top_n=15 (15 × 0.05 = 0.75 < 1.30 target long sum)
    thesis_alert_rho: 0.8
    borrow_cost_threshold: 0.05
```

No change to existing `tracks.A` or `tracks.B` structure.

---

## 4. Alert addition (Engineer adds to src/monitoring/telegram_alerts.py)

**Alert type:** `thesis_collapse`

**When:** Called from `rebalance_long_short` when `check_thesis_integrity` returns `thesis_alert=True`.

**Payload:** `{"rho": <float>, "reason": <str>}` (and any extra fields the formatter needs).

**Message format (Markdown):**  
`⚠️ *Thesis Alert — Long/Short Decoupling*\nCorrelation ρ={rho:.3f} (threshold: 0.80)\nLong and short baskets trading in lockstep — edge degrading\nGross exposure reduced 50%\nReason: {reason}`

Add a new `elif alert_type == "thesis_collapse":` branch in `send_alert`, after existing branches (e.g. after `ic_degradation`), using the same pattern as other alert types (payload keys `rho`, `reason`; format the string as above).

---

## 5. Integration notes (Track D and existing tracks A/B/C)

- **No change to Tracks A/B:** `model_config.yaml` only gains `tracks.D`. Existing code that reads `tracks.A` or `tracks.B` (e.g. `model_path`) is unchanged. No new code path is executed for A/B.
- **Track C:** If present elsewhere, leave unchanged. This spec does not define or modify Track C.
- **Entry point:** The Engineer will wire Track D so that when the system runs in “Track D” mode (e.g. `--track D` or config `active_track: D`), the pipeline uses `rebalance_long_short` instead of (or in addition to) the existing long-only `compute_target_weights` path. Exact entry point (e.g. backtest script, weekly rebalance script) is not changed by this spec; only the existence of `src/portfolio/long_short_optimizer.py` and the four functions is specified.
- **Regime status and vix_z:** `outputs/regime_status.json` currently does not include `vix_z`. Optionally, the Engineer may add `vix_z` to the payload in scripts/regime_monitor.py (where it is already computed at lines 79–84) so that `rebalance_long_short` can read it directly; otherwise, the fallback in §2 Function 4 (compute from VIX history) must be implemented.
- **HRP reuse:** Long-side weights must use the same HRP methodology as scripts/portfolio_optimizer.py (HRPOpt, ward linkage, same lookback/min_obs). Prefer extracting a small helper (e.g. `get_hrp_weights(returns_df)`) used by both the script and long_short_optimizer to avoid drift.

---

**End of spec.**
