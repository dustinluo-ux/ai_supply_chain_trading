# ML IC Gate — Diagnosis (Phase 3)

**Timestamp:** 2026-02-21  
**Context:** Phase 3 ML IC gate FAIL (IC=0.0164, threshold 0.02). Pipeline: `scripts/train_ml_model.py`, `src/models/train_pipeline.py`.  
**Reference:** docs/INDEX.md. Evidence discipline: all claims cite file:line.  
**Deliverable:** Read and document only; no code.

---

## Config: model_config.yaml (train/test and model)

**File:** `config/model_config.yaml`

- **Train period:** `train_start: '2022-01-01'`, `train_end: '2023-12-31'` (lines 53-54).
- **Test period:** `test_start: '2024-01-01'`, `test_end: '2024-12-31'` (lines 55-56).
- **Active model:** `active_model: 'ridge'` (line 8); ridge hyperparameters at lines 15-16 (`alpha: 1.0`).
- **Features:** `feature_names`: momentum_avg, volume_ratio_norm, rsi_norm, news_supply, news_sentiment (lines 44-48).

---

## Bug 1: TICKERS list vs canonical watchlist

**Suspected:** `scripts/train_ml_model.py` TICKERS list contains AAPL, MSFT, GOOGL; verify whether these match the canonical watchlist in `config/data_config.yaml` or `config/strategy_params.yaml`.

**Evidence:**

- **scripts/train_ml_model.py:33-34** — `cfg = get_config()`; `tickers = cfg.get_watchlist()`. No hardcoded TICKERS list; tickers are loaded from config.
- **scripts/train_ml_model.py:35** — `load_prices(data_dir, tickers)` uses that list.
- **config/data_config.yaml:33** — `watchlist: ["NVDA", "AMD", "TSM", "AAPL", "MSFT", "GOOGL"]`. This is the canonical watchlist (see **src/utils/config_manager.py** `get_watchlist()` which reads `data_config.universe_selection.watchlist`).
- **config/strategy_params.yaml** — No `watchlist` key. Contains `entity_ticker_map` (LLM entity names → tickers), propagation/warmup/execution params; not a ticker universe source.

**Verdict:** **REFUTED.** The training script uses the canonical watchlist from config. AAPL, MSFT, GOOGL are in that watchlist (data_config.yaml:33), so the script and config match. strategy_params.yaml does not define a watchlist.

---

## Bug 2: _extract_features() news fallback 0.0 vs 0.5

**Suspected:** Fallback values for `news_supply` and `news_sentiment` when no news is found are 0.0; Phase 3 policy (CLAUDE.md) requires pre-2025 neutral default 0.5.

**Evidence:**

- **CLAUDE.md (Phase 3 Pivot):** “Pre-2025 (training): … `news_supply` and `news_sentiment` features default to **0.5** (neutral) for all 2022–2024 training rows.”
- **src/models/train_pipeline.py:141-142** — In `_extract_features()`:
  - `news_supply = float(news.get('supply_chain_score', news.get('supply_chain', 0.5)))`
  - `news_sentiment = float(news.get('sentiment_score', news.get('sentiment', 0.5)))`
  Default when keys are missing is **0.5**. Docstring at 109 also states “News from news_signals (default 0.5 = neutral).”

**Verdict:** **REFUTED.** Fallback is already 0.5 per Phase 3 policy.

---

## Bug 3: evaluate_ic() anchored walk-forward vs single held-out

**Suspected:** evaluate_ic() may use a single held-out window; CLAUDE.md / project policy specifies anchored walk-forward for the IC gate.

**Evidence:**

- **docs/DECISIONS.md:102** — “Gate before wiring: Measure IC … **on anchored walk-forward**. Require IC ≥ 0.02 before integrating into live system.”
- **src/models/train_pipeline.py:205-281** — `evaluate_ic()`:
  - Accepts `test_start`, `test_end`.
  - Calls `prepare_training_data(..., train_start=test_start_dt, train_end=test_end_dt)` once (lines 216-223), producing a single `(X_test, y_test, meta)`.
  - Runs `model.predict(X_test)` once and a single `spearmanr(pred, y_test)` (lines 226-228).
  No loop over time windows, no expanding/rolling train then test, no TimeSeriesSplit or multi-window IC aggregation.

**Verdict:** **CONFIRMED.** evaluate_ic() implements a **single held-out window**, not anchored walk-forward. Policy requires anchored walk-forward (DECISIONS.md:102).

---

## Additional root causes (from reading)

- **Single test window variance:** One Spearman over the full 2024 test block is a single sample; IC=0.0164 may be noise. Anchored walk-forward would yield multiple out-of-sample ICs and a more stable gate (e.g. mean/median IC ≥ 0.02).
- **Train/test regime:** Train 2022–2023, test 2024 only. If 2024 is structurally different (e.g. single regime), the single-window IC may not reflect robustness across regimes; walk-forward would partially address this.
- **Sample size:** With six tickers and weekly samples, test set size is limited; a single low IC can be sensitive to a few ticker-weeks. No additional bug found in date ranges or feature defaults given current code.

---

## Ordered fix list for the Engineer

1. **Implement anchored walk-forward IC (Bug 3)**  
   - **Where:** `src/models/train_pipeline.py`, method `evaluate_ic()`.  
   - **What:** Replace single test-window evaluation with an anchored walk-forward procedure: e.g. expanding window (train on data up to time T, predict on next period, compute IC per window; repeat); then report a summary IC (e.g. mean or median of per-window ICs) and apply the gate to that.  
   - **Policy source:** docs/DECISIONS.md:102 — “Measure IC … on anchored walk-forward. Require IC ≥ 0.02.”

2. **Keep current behavior for tickers and news defaults**  
   - **Tickers:** scripts/train_ml_model.py already uses `get_config().get_watchlist()`; no change needed. Canonical watchlist is config/data_config.yaml (universe_selection.watchlist). config/strategy_params.yaml does not define a watchlist.  
   - **News fallback:** src/models/train_pipeline.py:141-142 already use 0.5; no change needed. Policy: CLAUDE.md Phase 3 Pivot (pre-2025 neutral = 0.5).

3. **Re-run and document**  
   - After implementing walk-forward IC, run `python scripts/train_ml_model.py`, record the reported IC (and, if implemented, per-window or summary IC), sample counts, and PASS/FAIL in docs/ml_ic_result.md or as per project validation process.

---

## Evidence summary

| Bug | Question | Verdict | Evidence (file:line) |
|-----|----------|---------|----------------------|
| 1 | TICKERS vs canonical watchlist (data_config / strategy_params) | REFUTED | train_ml_model.py:33-35 uses get_watchlist(); data_config.yaml:33 watchlist includes AAPL, MSFT, GOOGL; strategy_params.yaml has no watchlist |
| 2 | news_supply / news_sentiment fallback 0.0 vs 0.5 | REFUTED | train_pipeline.py:141-142 default 0.5; docstring :109 |
| 3 | evaluate_ic anchored walk-forward vs single held-out | CONFIRMED | train_pipeline.py:205-281 single prepare_training_data + single spearmanr; DECISIONS.md:102 requires anchored walk-forward |

---

## Iteration 2 — Root Cause and Fix Plan

**Context (validator output):** docs/ml_ic_result.md — walk-forward mean IC = -0.0058 (FAIL). Feature importance: Ridge coefficients collapsed to ~0.0000 except rsi_norm (0.0066). Two structural issues diagnosed below.

---

### ISSUE 1 — Label noise (raw return mixes alpha with market beta)

**Evidence:**

- **src/models/train_pipeline.py:146-158** — `_calculate_forward_return()` returns raw 1-week forward return:
  - `price_current = close.asof(date)`, `price_future = close.asof(future_date)` (date + 7 days).
  - Return = `(price_future - price_current) / price_current` (line 156).
  - No cross-sectional or market adjustment. The label is therefore raw absolute return, which conflates stock-specific alpha with market/sector beta (e.g. in a 6-stock semiconductor set, a broad market move moves all labels together and dominates cross-sectional rank).
- **src/models/train_pipeline.py:74-89** — `prepare_training_data()` builds `y_list` by appending each `_calculate_forward_return(...)` result (line 84). Labels are used as-is for training and for IC; no per-date normalization.

**Proposed change:**

- **What:** Change the training (and evaluation) label from raw 1-week forward return to **cross-sectional z-score return** at each weekly date.
- **Method:** For each weekly date in the training batch, over all tickers that have a valid forward return for that date: compute mean and std of those forward returns; replace each label with (return − mean) / std. If std is 0 for a date, use 0.0 or drop that date’s samples (document chosen behavior). Apply the same transformation when building test labels in the walk-forward so train and test labels are comparable.
- **Where:** In `prepare_training_data()` (src/models/train_pipeline.py): after assembling `X_list`, `y_list`, `meta_list` (lines 71-89), add a step that groups by date (using `metadata['date']` or equivalent), computes per-date mean and std of forward returns, and overwrites the values in `y_list` (and in `metadata['forward_return']` if kept for logging) with the z-scores. Ensure the same date-grouped z-score logic is used for any data prepared for evaluation (e.g. test folds in `evaluate_ic()` use the same definition: per test-date cross-sectional z-score within the test window).
- **Config:** No config key change; label definition is pipeline logic.

**Expected effect:** Removes market/sector beta from the label, so the target becomes “relative rank within the semiconductor group” — appropriate for a 6-stock sector-rotation model. Reduces label noise and should improve Spearman IC stability across folds and a more interpretable signal (direction: **IC expected to improve and become more stable**).

---

### ISSUE 2 — Over-regularization (Ridge alpha too strong)

**Evidence:**

- **config/model_config.yaml:15-16** — `models.ridge.alpha: 1.0` (comment: “Regularization strength”).
- **docs/ml_ic_result.md (§5 Feature importance)** — Ridge coefficients: rsi_norm 0.0066; momentum_avg, volume_ratio_norm, news_supply, news_sentiment all 0.0000. Train/Val R² near zero (e.g. Train R² 0.0002, Val R² -0.0039 to -0.0180). This is consistent with strong L2 shrinkage driving most coefficients to zero; only one feature retains a small non-zero weight.

**Proposed change:**

- **Config key:** `config/model_config.yaml` → `models.ridge.alpha`.
- **Value:** Change from `1.0` to `0.01`.
- **Reason:** Features are already normalized to [0,1] (technical_library normalization; news 0.5 default). With 5 features and ~500 training samples (e.g. 499 train in first fold per ml_ic_result.md), alpha=1.0 imposes a shrinkage penalty on the same order as the typical squared coefficient scale, effectively squashing coefficients. Reducing alpha to 0.01 gives the model room to assign non-trivial weights to momentum_avg, volume_ratio_norm, and news features without removing regularization entirely.

**Expected effect:** Coefficients can move away from zero; feature importance should show non-zero weights for more than one feature when signal exists. **IC expected to improve** (direction: less shrinkage bias, more signal expressed in predictions).

---

### Iteration 2 summary

| Issue | Location (file:line or config) | Proposed change | Expected IC direction |
|-------|--------------------------------|-----------------|------------------------|
| 1. Label noise | train_pipeline.py:146-158 (_calculate_forward_return), :74-89 (prepare_training_data) | Label = cross-sectional z-score of forward return per weekly date; apply in prepare_training_data (and consistently for test data in evaluate_ic) | Improve; more stable across folds |
| 2. Over-regularization | config/model_config.yaml:16 (models.ridge.alpha) | Set `alpha: 0.01` (from 1.0) | Improve (coefficients can express signal) |

---

*Diagnosis only. No code changes. Engineer implements Iteration 2 fixes per this section.*

---

## Phase 3 Wiring Plan

**Context:** IC gate passed (IC=0.0286). Saved model: `models/saved/ridge_20260221_131840.pkl`. This section identifies the exact wiring point for the ML blend and documents the integration plan. Evidence discipline: file:line for all claims.

---

### 1. SignalEngine — where Master Score is produced

**File:** `src/signals/signal_engine.py`

- **Where produced:** Per-ticker score is written in the backtest path in the Phase 3 loop (lines 319–341). For each ticker `t` in `extended_universe`, `compute_signal_strength(entry["row"], ...)` returns `(score, _)` and the value is assigned at **line 339:** `week_scores[t] = score`. In the weekly path, scores come from `SignalCombiner.get_top_stocks` and are built into a dict at **lines 414–418** (`scores = dict(zip(top_stocks["ticker"].astype(str), top_stocks[score_col].fillna(0.5).tolist()))`).
- **Range:** Master score is in **[0, 1]** (technical_library `compute_signal_strength` and docstring at signal_engine.py:74: “scores: ticker -> master score”).
- **Data structure:** **`dict[str, float]`** — ticker symbol → numeric score. Variable name in backtest path: `week_scores` (line 162); returned as first element of the tuple.
- **Method that returns it to caller:** **`SignalEngine.generate(as_of_date, universe, data_context)`** at **lines 66–79**. It returns `tuple[dict[str, float], dict[str, Any]]`, i.e. `(scores, aux)`. Callers receive the per-ticker scores as the first element of that tuple.

---

### 2. Target weight pipeline — where scores are consumed

**File:** `src/core/target_weight_pipeline.py`

- **Where consumed:** **Line 132:** `week_scores, aux = signal_engine.generate(as_of, tickers, data_context)`. So `week_scores` is the `dict[str, float]` of per-ticker scores from SignalEngine.
- **Between score receipt and weight assignment:**  
  - **Lines 135–143:** `policy_context` is built from regime/SPY/kill-switch data; then **line 143:** `gated_scores, _ = policy_engine.apply(as_of, week_scores, aux, policy_context)`. So `week_scores` are passed directly into `PolicyEngine.apply()` and become `gated_scores`.  
  - **Lines 145–147:** `portfolio_context` is built (top_n, atr_norms, tickers); then **line 147:** `intent = portfolio_engine.build(as_of, gated_scores, portfolio_context)`. Weights are derived from `gated_scores` inside `PortfolioEngine.build()`.  
  So the flow is: **week_scores → PolicyEngine.apply() → gated_scores → PortfolioEngine.build() → intent → weights**.

---

### 3. use_ml flag

**File:** `config/model_config.yaml`

- **Location:** **Line 5** — key `use_ml`, under the top-level mapping (no nested key).
- **Current value:** **`false`** (comment: “Set to true to enable ML predictions”).

---

### 4. BaseReturnPredictor — load_model and predict

**File:** `src/models/base_predictor.py`

- **load_model:** **Lines 196–219** — `@classmethod def load_model(cls, path: str) -> 'BaseReturnPredictor'`. Loads a pickle from `path`, reconstructs the instance from `save_data` (model_name, model_type, feature_names, config, model, is_trained, etc.), and returns the predictor instance. So **`BaseReturnPredictor` has a `load_model()` classmethod** that loads a saved pkl. Subclasses (e.g. RidgeReturnPredictor) inherit it; calling `RidgeReturnPredictor.load_model(path)` returns a Ridge instance. The saved pkl includes `model_type`; a loader that does not know the class ahead of time can read the pkl once to get `model_type`, then call `MODEL_REGISTRY[model_type].load_model(path)` (see model_factory.py MODEL_REGISTRY).
- **predict:** **Lines 128–131** — `def predict(self, X: np.ndarray) -> np.ndarray`. Accepts `X` with shape `(n_samples, n_features)`; returns `self.model.predict(X)`, which for sklearn regressors is a 1D array of shape `(n_samples,)`. So **predict() accepts a 2D numpy array and returns a 1D array**.

**File:** `src/models/model_factory.py` — No `load_model()` today; only `create_model()` (lines 26–57) and `list_available_models()` (59–61). To load by path without hardcoding the class, the integration will need either a new factory function that reads the pkl’s `model_type` and calls the appropriate class’s `load_model(path)`, or the caller to pass model type + path from config.

---

### Exact hook point for ML blend

- **File and line:** **`src/core/target_weight_pipeline.py`**, **after line 132, before line 143.**  
  That is: after `week_scores, aux = signal_engine.generate(as_of, tickers, data_context)` and before `gated_scores, _ = policy_engine.apply(as_of, week_scores, aux, policy_context)`.
- **Data structure at that point:** `week_scores` is **`dict[str, float]`** (ticker → baseline Master Score in [0, 1]). `aux` is `dict` with at least `atr_norms`, `regime_state`, `news_weight_used`, `buzz_by_ticker`. `prices_dict` and `as_of` (and `tickers`) are in scope so features can be built for the same date and universe.

**Intent:** When `use_ml` is true, compute ML scores for each ticker, normalize them to [0, 1], blend with `week_scores` per DECISIONS.md (0.7 × Baseline + 0.3 × ML_Score), apply the sanity check (e.g. baseline bullish and ML bearish → reduce exposure), then pass the **blended** dict into `policy_engine.apply()` instead of the raw `week_scores`. So the variable passed to `policy_engine.apply()` becomes the blended scores (same type `dict[str, float]`).

---

### Step-by-step integration sequence

1. **Load model**  
   - Read `config/model_config.yaml`: `use_ml`, model path (e.g. from `training.model_save_dir` + configured or “latest” filename, or a dedicated `inference.model_path`).  
   - If `use_ml` is false, skip ML and pass `week_scores` unchanged to PolicyEngine.  
   - If true: load the pkl. Either call the concrete class (e.g. `RidgeReturnPredictor.load_model(path)` if config says ridge), or add/use a factory helper that reads the pkl’s `model_type`, then calls `MODEL_REGISTRY[model_type].load_model(path)`.  
   - **Method:** `BaseReturnPredictor.load_model(path)` (on the appropriate subclass).

2. **Extract features**  
   - For `as_of_date` and each ticker in `tickers` (or the keys of `week_scores`), build the 5-feature vector in the same order as training: `[momentum_avg, volume_ratio_norm, rsi_norm, news_supply, news_sentiment]`.  
   - Use the same logic as in **`src/models/train_pipeline.py`** `_extract_features()` (lines 106–144): slice prices up to `as_of_date`, call `calculate_all_indicators`, take last row, derive momentum_avg from momentum_5d_norm and momentum_20d_norm, and get news from `news_signals` or default 0.5.  
   - Produce a 2D array `X` of shape `(n_tickers, 5)` and preserve ticker order so predictions align to tickers.  
   - **Methods:** Reuse or call into `ModelTrainingPipeline._extract_features()` per (ticker, as_of_date, prices_dict, news_signals), or add a small helper e.g. `get_features_for_date(as_of_date, tickers, prices_dict, news_signals)` that returns `(X, ticker_list)`.

3. **Predict**  
   - Call **`model.predict(X)`** (BaseReturnPredictor.predict at base_predictor.py:128–131).  
   - Result: 1D array of length `n_tickers` (raw predicted returns).

4. **Normalize**  
   - Convert raw ML predictions to a **0–1 score** per DECISIONS.md: “Convert ML predicted return to 0–1 score using rolling Z-score (3–6 month window) passed through a min-max clipper.”  
   - For the first integration, if no rolling window of past predictions exists, use a cross-sectional normalization (e.g. Z-score of current predictions across tickers, then min-max to [0, 1]) so that the ML output is a score in [0, 1] comparable to the baseline.  
   - Produce `dict[str, float]` ticker → ML score in [0, 1], keyed by the same ticker order as `X`.

5. **Blend**  
   - For each ticker: **blended[t] = 0.7 × week_scores[t] + 0.3 × ml_score[t]** (DECISIONS.md).  
   - Use blended as the new score dict to pass downstream.

6. **Sanity check**  
   - Per DECISIONS.md: “If ML predicts negative return but Baseline is bullish, reduce position size by 50%.”  
   - Interpretation: where baseline (week_scores[t]) is “bullish” (e.g. > 0.5) and ML score is “bearish” (e.g. < 0.5), apply a 0.5 multiplier to the blended score (or to the final weight when building intent). Document the chosen rule (e.g. blended[t] *= 0.5 for those tickers).

7. **Pass to policy**  
   - Call **`policy_engine.apply(as_of, blended_scores, aux, policy_context)`** instead of `policy_engine.apply(as_of, week_scores, aux, policy_context)`.  
   - Rest of the pipeline (PortfolioEngine.build, weights Series) unchanged.

---

### Files that will need to change

- **config/model_config.yaml** — Ensure a way to select the saved model for inference (e.g. `use_ml: true` and a path or “latest” under `training.model_save_dir` or a new `inference.model_path`).
- **src/core/target_weight_pipeline.py** — Add the ML branch: after `signal_engine.generate()`, if use_ml then load model, extract features, predict, normalize, blend, sanity check, and pass blended scores into `policy_engine.apply()`; otherwise pass `week_scores` as today.
- **src/models/train_pipeline.py** (or a shared feature module) — Expose feature extraction for one date and N tickers (e.g. `get_features_for_date(...)` or callable that returns `(X, ticker_order)`) so the pipeline can build the inference feature matrix without duplicating logic.
- **src/models/model_factory.py** — Optional but recommended: add `load_model(path: str) -> BaseReturnPredictor` that reads the pkl to get `model_type`, then calls `MODEL_REGISTRY[model_type].load_model(path)` so the pipeline has a single entry point for loading by path.

---

*Documentation only. No code changes in this task.*

---

## Task 6 Wiring Plan — Watchlist purge + volatility filter + generate_daily_weights.py

**Context:** Task 6 adds a volatility filter (design below) and a script `generate_daily_weights.py`. This section verifies exact hook points and config locations before implementation. Evidence discipline: file:line for all claims.

---

### 1. target_weight_pipeline.py — ML blend end and vol filter insertion point

**File:** `src/core/target_weight_pipeline.py`

- **Where the ML blend step ends:** The last line of the blended_scores block is **line 193:** `scores_to_use = _blended`. That assignment completes the Phase 3 ML branch (when `use_ml` is true and model/pipeline loaded successfully).
- **Next line after it (where vol filter must be inserted before):** **Line 195:** `policy_context = {`. So the volatility filter must run **after line 193** and **before line 195**. The filter will read `scores_to_use` (and optionally `prices_dict`), apply the vol rule, and overwrite or replace `scores_to_use` with the scaled scores before `policy_engine.apply(as_of, scores_to_use, aux, policy_context)` at line 202.
- **prices_dict in scope:** **Yes — directly in scope.** `prices_dict` is a parameter of `compute_target_weights` at **line 47:** `prices_dict: dict[str, pd.DataFrame]`. It is not only inside `data_context`; it is a top-level argument, so the vol filter can use `prices_dict` and `as_of` to compute per-ticker 20d realized vol and the 252-day rolling percentile without reading from `data_context`. `data_context` also contains `"prices_dict": prices_dict` at **line 125**, but the function already has `prices_dict` in local scope.

---

### 2. technical_master_score.yaml — risk scaling / filter config home

**File:** `config/technical_master_score.yaml`

- **Existing sections:** The file contains: weight_mode, category_weights, news_weight, BULL_WEIGHTS / DEFENSIVE_WEIGHTS / BEAR_WEIGHTS / SIDEWAYS_WEIGHTS, rolling_window (252), and categories (indicator → category mapping). There is **no** section for “risk scaling” or “position sizing filters” or “volatility_filter”.
- **Right home for volatility_filter?** technical_master_score.yaml is the single source of truth for **scoring** (Master Score weights, regime weights, normalization window). The volatility filter is a **score modifier** (like the ML blend or sideways_risk_scale): it scales `scores_to_use` before PolicyEngine. So either:
  - **Option A:** Add a new top-level section **`volatility_filter`** in **config/technical_master_score.yaml** — consistent with “score pipeline” and same file used by technical_library / signal scoring.
  - **Option B:** config/trading_config.yaml already has **position_sizing** (lines 35–38) for ATR-based sizing; it does not own “score scaling” filters. config/strategy_params.yaml has **rebalancing** (drift_threshold, min_trade_dollar_value, etc.) and **circuit_breaker** — runtime risk/execution, not pre-weight score filters.
- **Recommendation:** Put **volatility_filter** in **config/technical_master_score.yaml** as a new section. It is a scoring/risk overlay on the signal (same pipeline stage as Master Score and ML blend), not execution or position-sizing. If the project later centralizes all “runtime risk parameters” in one file, that can be a separate decision; today no single config “owns” score-level risk filters, and technical_master_score is the natural place for score-pipeline parameters.

---

### 3. technical_library.py — daily log returns or 20-day realized vol column

**File:** `src/signals/technical_library.py`

- **calculate_all_indicators():** The function is defined at **lines 137–348** (docstring at 140: “Ingest a standard OHLCV DataFrame; return OHLCV + all indicators + normalized columns”). It builds an `out` dict/DataFrame with columns from pandas_ta: trend (MACD, ADX), momentum (RSI, willr, stoch, roc, cci, momentum_5d_norm, momentum_20d_norm), volume (volume_ratio_norm, cmf, obv), volatility (**atr_norm**, **bb_position_norm**). See _DEFAULT_CATEGORIES at lines 80–85 and the normalization logic that produces `*_norm` columns.
- **Daily log returns or 20-day realized volatility?** There is **no** column for daily log returns or for 20-day realized volatility (e.g. std of log returns × √252). The volatility category exposes **atr_norm** (ATR-based, 14-period) and **bb_position_norm** (Bollinger Band position), not annualized realized vol from log returns. So the filter **cannot** reuse an existing column; the Engineer must **compute** std(log_returns, 20d) × √252 from `close` (e.g. in the pipeline or in a small helper). Adding a `realized_vol_20d` (or similar) to `calculate_all_indicators()` would avoid recomputation in the pipeline if desired later.

---

### 4. run_execution.py — arguments and successful mock output

**File:** `scripts/run_execution.py`

- **Arguments:** Defined in **lines 164–174.** The parser accepts:
  - **--tickers** (required): comma-separated tickers (e.g. AAPL,NVDA,SPY).
  - **--date**: optional signal date YYYY-MM-DD; default: latest Monday in data.
  - **--top-n**: default 3 (top N for portfolio).
  - **--sideways-risk-scale**: default 0.5.
  - **--mode**: default "mock", choices ["mock", "paper"].
  - **--confirm-paper**: with paper mode, actually submit orders; without: dry-run.
  - **--rebalance**: use last valid weights from cache; propose trades only for drift.
  - **--check-fills**: skip execution; read fill ledger and (in paper) query IB for order status.
- **Successful mock run (no --check-fills, no --rebalance):** After computing target weights (via `compute_target_weights` at 256–263), building intent, and building executable delta_trades (379–383), the script prints (lines 386–396):
  - A header: `--- Canonical execution (mock): delta trades ---`
  - `As-of:       {as_of.date()}`
  - `Account:     {account_value:,.2f}`
  - `Intent:      {intent.tickers}`
  - `Executable:  {len(executable)}`
  - One line per executable row: `BUY/SELL {quantity} {symbol} (delta_w=... drift=...)`
  - Then (line 311): `(Mock: no orders submitted.)`
  - Returns `(0, current_run_fills)` (line 443). So **generate_daily_weights.py** must replicate or call the same spine to get **daily (or as-of) target weights**; it may output a table (date, ticker, weight) instead of executing, and can share `compute_target_weights` from target_weight_pipeline (as run_execution does at 127–141).

---

### Volatility filter design (feasibility)

- **Logic:** After ML blend (i.e. after `scores_to_use` is set): for each ticker compute **std(log_returns, 20d) × √252** (20-day realized vol, annualized). Compare that value to the **252-day rolling history** of the same metric for that ticker. If today’s value **> 95th percentile** of that history → **scores_to_use[t] *= 0.5**.
- **Config keys:** `volatility_filter.enabled`, `lookback_days: 252`, `percentile_threshold: 95`, `scale_factor: 0.5`. Feasible: hook point is after line 193; `prices_dict` and `as_of` are in scope; no existing vol column in technical_library, so vol must be computed from `close` (log returns then rolling std × √252). No code written here — verification only.

---

### Task 6 wiring summary

| Item | Detail |
|------|--------|
| **Exact hook for vol filter** | **src/core/target_weight_pipeline.py** after **line 193** (`scores_to_use = _blended` or `week_scores`), before **line 195** (`policy_context = {`). Apply filter to `scores_to_use` in place or reassign. |
| **Config for volatility_filter** | **config/technical_master_score.yaml** — add new top-level section **`volatility_filter`** with keys: `enabled`, `lookback_days` (252), `percentile_threshold` (95), `scale_factor` (0.5). |
| **technical_library vol column** | **No.** calculate_all_indicators() does not expose daily log returns or 20-day realized volatility. Engineer must compute std(log_returns, 20d)×√252 from `close` (in pipeline or helper). |
| **generate_daily_weights.py interface** | **Inputs:** tickers (from config watchlist or CLI), date range or single date, data_dir (or from data_config). **Output:** table of (date, ticker, weight) — e.g. CSV/DataFrame with columns date, ticker, target_weight. **Call path:** Call **target_weight_pipeline.compute_target_weights(as_of, tickers, prices_dict, data_dir, ...)** for each as_of date (same as run_execution.py does at 256–263); do not call run_execution.py itself (that script does execution, fill ledger, and CLI for mode/confirm-paper). So generate_daily_weights.py is a **weights-only** script: load prices → for each date call compute_target_weights → write weights table. |

---

### Files that will change (Task 6)

- **config/technical_master_score.yaml** — Add section `volatility_filter` with enabled, lookback_days, percentile_threshold, scale_factor.
- **src/core/target_weight_pipeline.py** — After ML blend (after line 193), before policy_context (before line 195): if volatility_filter.enabled, compute per-ticker 20d realized vol and 252d rolling percentile, apply scale_factor to scores_to_use where vol > threshold.
- **scripts/generate_daily_weights.py** — New script: load config (watchlist, data_dir), load prices, loop over dates, call compute_target_weights, output (date, ticker, weight) table.
- **config/data_config.yaml** (or watchlist source) — If “watchlist purge” is a separate change (e.g. remove certain tickers from universe_selection.watchlist), that file may change; otherwise no change required for vol filter or generate_daily_weights alone.

---

*Documentation only. No code changes in this task.*

---

## Task 7 Architecture — Daily workflow + performance tracker + generate_daily_weights enhancement

**Reference:** INDEX.md; Evidence discipline (file:line). Verifies existing hooks before implementation. No code — document only.

---

### 1. update_price_data.py and update_news_data.py

**scripts/update_price_data.py**

- **CLI arguments:** **Lines 111-121** — `--tickers` (default None; comma-separated, else watchlist from config), `--start` (default "2015-01-01"), `--end` (default today), `--delay` (default 1.0).
- **Exit / return:** **Lines 207, 212** — `return 0 if failed == 0 else 1`; **line 212:** `sys.exit(main())`. So it exits 0 on success (no failed tickers), 1 if any failed. Returns an int from main().
- **Subprocess vs import:** Can be called via **subprocess** (script is self-contained, exits with 0/1). No need to import and call as functions unless the daily workflow wants to avoid process spawn; subprocess is sufficient and keeps process isolation.

**scripts/update_news_data.py**

- **CLI arguments:** **Lines 46-57** — `--tickers` (default None), `--start` (default 7 days ago), `--end` (default today), `--delay` (default 1.0).
- **Exit / return:** **Lines 123, 128** — `return 0 if failed == 0 else 1`; **line 128:** `sys.exit(main())`. Exits 0 on success, 1 if any failed.
- **Subprocess vs import:** Same as update_price_data: can be run via subprocess; no API contract that requires import. Subprocess is appropriate for a daily workflow script.

**Subprocess vs import decision:** Use **subprocess** to run both update scripts from daily_workflow.py (or equivalent). They are designed as CLI entry points, return 0/1, and do not expose a callable API that the workflow needs to reuse in-process.

---

### 2. generate_daily_weights.py — stdout, return value, hook points

**Current stdout (column names, format):**

- **Lines 88-91** — Writes CSV to stdout: **header row** `["date", "ticker", "target_weight", "latest_close", "notional_units"]` (line 89), then one **data row per ticker** (line 90) with (date_str, ticker, w, latest_close, notional_units). Format is CSV (csv.writer(sys.stdout)).
- **Return value:** **Line 92** — `return 0`. The script returns only an exit code; it does **not** return a structured object. All output is **stdout-only** (plus stderr for errors/warnings).

**Best place to add:**

- **(a) CSV append to outputs/daily_signals.csv:** After building `rows` (lines 74-86) and before or in addition to writing to stdout. Recommended: **after line 86** (after `rows` is fully built), open `outputs/daily_signals.csv` in append mode and write the same rows (optionally with the same or an extended schema). Alternatively write the same CSV to the file first, then also write to stdout for piping. Keep a single source of truth for the row list (lines 74-86) and write it to both file and stdout.
- **(b) Terminal summary table (master_score + vol level per ticker):** The script currently does not have master_score or 20d vol; those would come from the pipeline if exposed (see §3). The best place to print a summary table is **after** the main CSV output (after line 91), before `return 0` (line 92). That requires the script to have access to per-ticker master_score and 20d vol — either from an extended return value of compute_target_weights() or from a separate call/helper. So (b) depends on §3; the **hook** for printing is after the CSV block, before return.

---

### 3. compute_target_weights() — return value and exposing scores/vol

**What it currently returns:**

- **Signature and return:** **src/core/target_weight_pipeline.py:45-56, 264** — Returns **only** `pd.Series(weights)` indexed by the requested tickers (line 264: `return pd.Series(weights).reindex(list(tickers), fill_value=0.0)`). The function does **not** return aux data, scores, or vol values. It uses `week_scores` (line 139), `aux` (e.g. atr_norms at 140), and inside the vol filter block (lines 206-224) it computes `_today_vol` per ticker but does not expose it; it only mutates `scores_to_use`.

**To expose per-ticker master_score and 20d vol for the summary table:**

- **Option A — New return value:** Extend the return to a tuple, e.g. `(weights_series, aux_dict)` where `aux_dict` contains at least `scores` (master or gated scores keyed by ticker) and `vol_20d` (or similar) keyed by ticker. The vol filter block already computes `_today_vol` per ticker (line 223); that could be collected into a dict and returned. Scores are available as `scores_to_use` (or `gated_scores`) before building intent. This would require a **return-value change** to compute_target_weights() and updates to all callers (run_execution.py, generate_daily_weights.py, any backtest entry that uses it).
- **Option B — Caller reads from signal_engine / recomputes:** The caller could call SignalEngine.generate() and the vol formula separately. That duplicates pipeline logic and is brittle. Not recommended.
- **Conclusion:** To expose master_score and 20d vol for the summary table without duplicating logic, **compute_target_weights() needs a return-value change** (e.g. return a small struct or tuple that includes weights plus optional scores and vol_20d dicts). There is no existing "other way" that already exposes them; the pipeline does not currently return aux/scores/vol.

---

### 4. SPY price data availability

- **Config:** **config/data_config.yaml:8, 33** — `data_sources.data_dir` is set (e.g. `"C:/ai_supply_chain_trading/trading_data/stock_market_data"`); **line 33:** `benchmark: "SPY"` under universe_selection. So SPY is the configured benchmark; it is not in the watchlist (Task 6 purge).
- **Loading SPY:** **src/data/csv_provider.py:78-87** — `load_prices(data_dir, tickers)` uses `find_csv_path(data_dir, t)` for each ticker (line 85). **find_csv_path** (lines 43-75) walks `base_dir` and searches for `{TICKER}.csv`; subdirs are not hardcoded in find_csv_path (it uses os.walk). So `load_prices(Path(data_dir), ["SPY"])` will load SPY if a file `SPY.csv` exists under `data_dir`. **scripts/update_price_data.py:33, 130-134** — REQUIRED_TICKERS includes "SPY" and the script always appends SPY to the ticker list and writes to the same data_dir, so running update_price_data ensures SPY is present under that path.
- **Workspace check:** No `SPY.csv` under the project workspace (search for SPY.csv under trading_data/stock_market_data returned 0 files). The configured data_dir is an absolute path that may point outside the repo (e.g. C:/ai_supply_chain_trading/...). So **availability is environment-dependent**: it depends on data_dir existing and update_price_data (or manual placement) having created SPY.csv there.
- **Verdict:** **PASS (with caveat).** Config and code path support SPY (benchmark key, load_prices + find_csv_path). SPY is accessible via `load_prices(data_dir, ["SPY"])` if SPY.csv exists under data_dir. No SPY.csv in the workspace; actual availability depends on the configured data_dir and on having run update_price_data or otherwise placed SPY data. Document for the Engineer: ensure data_dir exists and run update_price_data at least once so SPY (and watchlist) CSVs are present.

---

### Task 7 summary

| Item | Conclusion |
|------|------------|
| **Subprocess vs import for update scripts** | Use **subprocess** to invoke update_price_data.py and update_news_data.py from daily_workflow; they exit 0 on success and do not require import. |
| **generate_daily_weights: CSV append** | Append to **outputs/daily_signals.csv** after building `rows` (after line 86), writing the same or extended schema; optionally also keep stdout CSV for piping. |
| **generate_daily_weights: summary table hook** | Print the terminal summary table (master_score + vol per ticker) **after** the CSV output block (after line 91), before `return 0`; requires scores/vol from pipeline (see below). |
| **compute_target_weights return-value change** | **Yes.** To expose master_score and 20d vol for the summary table without duplicating logic, the function must be extended to return (or include in a struct) scores and 20d vol in addition to the weights Series. |
| **SPY data** | **PASS (environment-dependent).** Config and code support SPY; load_prices(data_dir, ["SPY"]) works when SPY.csv exists under data_dir; run update_price_data to ensure SPY is present. |

---

### Files that will change or be created (Task 7)

- **scripts/daily_workflow.py** (new or existing) — Orchestrate update_price_data, update_news_data, then generate_daily_weights; call update scripts via subprocess; handle exit codes.
- **scripts/generate_daily_weights.py** — Add CSV append to outputs/daily_signals.csv (after building rows); add terminal summary table (after CSV output), using scores/vol from pipeline once exposed.
- **src/core/target_weight_pipeline.py** — Extend compute_target_weights() return value to include per-ticker scores (and optionally 20d vol) for use by generate_daily_weights and any other consumer that needs the summary table.
- **outputs/daily_signals.csv** — Created/appended by generate_daily_weights (ensure directory exists).
- **scripts/run_execution.py** (if it calls compute_target_weights) — Update caller to handle new return shape (e.g. unpack tuple or ignore extra fields) so the return-value change is backward-compatible or explicitly versioned.
- **Performance tracker** — If Task 7 includes a dedicated performance tracker (e.g. script or module that reads daily_signals and/or fills and produces metrics), list it as a new file under scripts/ or src/ per design.

---

*Documentation only. No code changes in this task.*
