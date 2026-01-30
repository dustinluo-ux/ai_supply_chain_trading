# Technical Specification

**Last Updated:** 2026-01-29

**Overlay strategy:** Regime and News Alpha are **multipliers/filters on top of** the base Master Score. No existing technical logic is removed.

Technical indicator math, Master Score (source of truth for technical signals), config, and signal-combination logic. Backtest execution details are in `BACKTEST_JOURNAL.md`.

---

## 1. Master Score (Source of Truth for Technical Signals)

**Module:** `src.signals.technical_library`  
**Config:** `config/technical_master_score.yaml`

The **Master Score** is the single source of truth for technical signals. Legacy RSI/Volume/Momentum formulas used in older backtests are superseded by this library for the Technical Library backtest (`scripts/backtest_technical_library.py`).

### 1.1 Normalization (No Look-Ahead)

- **Bounded indicators (RSI, Stochastic, Williams %R):** Static scaling only (e.g. `value / 100`). No future data.
- **Unbounded indicators (ATR, Volume Ratio, MACD, ROC, CCI, momentum, OBV, CMF, ADX, BB position):** Rolling 252-day min-max over the **past** window only. Normalized = `(x - rolling_min) / (rolling_max - rolling_min + ε)`, clipped 0–1; NaN → 0.5.

### 1.2 Category-Weighted Score

- **Categories and weights** (in `config/technical_master_score.yaml`): Trend 40%, Momentum 30%, Volume 20%, Volatility 10%.
- **Sub-score per category:** Mean of the `*_norm` values of indicators in that category (missing → 0.5).
- **Master Score:** `0.40×Trend + 0.30×Momentum + 0.20×Volume + 0.10×Volatility`.
- **Sizing:** Inverse-volatility weights use **ATR_norm from Signal Day − 1** (see `BACKTEST_JOURNAL.md`).

### 1.3 Indicators (pandas_ta)

Trend (MACD, ADX, PSAR, Aroon), Volatility (Bollinger, ATR, Keltner), Momentum (Stochastic, CCI, Williams %R, ROC, RSI(14), momentum 5d/20d), Volume (OBV, CMF, VWAP, volume ratio), Moving averages (EMA, SMA, golden cross). All normalized as above; config defines which `*_norm` map to which category.

### 1.4 Dynamic Weighting (Formal Engines)

Category weights can be **fixed**, **regime**, **rolling**, or **ml** (config: `weight_mode` in `config/technical_master_score.yaml`; backtest: `--weight-mode`). We use established quantitative libraries; no custom optimization or ML math from scratch.

- **fixed:** Use `category_weights` from config (e.g. 40/30/20/10).
- **regime:** **Engine: hmmlearn (3-State Regime).** `get_regime_hmm(close_series, as_of_date, n_components=3)` fits a **3-state Gaussian HMM** on SPY returns up to the signal date. **Transition matrix:** Fitted by Baum-Welch (EM); no look-ahead. **State mapping by mean return:** highest mean = BULL, lowest = BEAR, middle = SIDEWAYS. **Persistence check:** Backtest logs `[HMM TRANSITION MATRIX]` on the **first Monday** (once per run); **high diagonals (&gt; 0.80)** = stable regime; low diagonals = flip-flopping (transaction cost risk). **BULL** (high mean, low vol) → BULL_WEIGHTS; **BEAR** (negative mean, high vol) → DEFENSIVE_WEIGHTS, and CASH_OUT only when **BEAR and SPY &lt; 200-SMA** (dual-confirmation); **SIDEWAYS** (mean ~0, moderate vol) → SIDEWAYS_WEIGHTS, position size × 0.5. **Fallback:** If HMM fails, use SPY vs 200-SMA binary. Config: BULL_WEIGHTS, DEFENSIVE_WEIGHTS, SIDEWAYS_WEIGHTS.
- **rolling:** **Engine: PyPortfolioOpt.** Build a "category strategy returns" matrix (each column = one category; each row = sign(score − 0.5) × forward_ret). Then **EfficientFrontier** (max_sharpe) or **HRPOpt (Hierarchical Risk Parity)** to adjust category weights; when mode is rolling, HRPOpt can be used for regime-aware performance. **Safety:** `weight_bounds=(0.10, 0.50)` so no category &lt; 10% or &gt; 50%. `get_optimized_weights(..., method="max_sharpe"|"hrp")` in `src.signals.weight_model`. Only data from T−1 or earlier is used.
- **ml:** **Engine: Scikit-Learn.** Random Forest Regressor predicts **next-day return** from the 4 category sub-scores. **TimeSeriesSplit** is used for cross-validation so train folds are always strictly before test folds (No Look-Ahead rule). Feature importances from the CV-trained procedure are averaged and normalized as category weights. `get_ml_weights(history_df, lookback_days=60, n_splits=5)` in `src.signals.weight_model`.

**Safety:** All weight calculations for signal date T use only data from T−1 or earlier (no look-ahead).

### 1.5 API

- `calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame` — OHLCV + raw + `*_norm` columns.
- `compute_signal_strength(row, weight_mode=..., spy_above_sma200=..., regime_state=..., category_weights_override=..., news_composite=...) -> (master_score, result_dict)` — result includes `category_sub_scores`, `breakdown`. When `news_weight` &gt; 0, **Final_Score = (1 − news_weight) × Technical_Score + news_weight × News_Composite** (e.g. 0.8 × technical + 0.2 × news). When `weight_mode == "regime"`, `regime_state` in BULL/BEAR/SIDEWAYS selects BULL_WEIGHTS / DEFENSIVE_WEIGHTS / SIDEWAYS_WEIGHTS.
- `get_optimized_weights(history_df, lookback_days=60, forward_days=5, method="max_sharpe"|"hrp")` — rolling mode weights (PyPortfolioOpt); weight_bounds=(0.10, 0.50).
- `get_regime_hmm(close_series, as_of_date, min_obs=60, n_components=3)` — **3-State Regime** (hmmlearn GaussianHMM); returns `(state_label, info)` where `state_label` in `"BULL"`|`"BEAR"`|`"SIDEWAYS"`; **mapping by mean return:** highest mean = BULL, lowest = BEAR, middle = SIDEWAYS. `info` has `state`, `mu`, `sigma`, `transmat`, `transmat_labels`. Fallback: (None, None) → use SPY vs 200-SMA binary.
- `get_ml_weights(history_df, lookback_days=60, n_splits=5)` — ML mode weights (Scikit-Learn RF + TimeSeriesSplit CV); returns `(weights, cv_r2)`; if CV R² &lt; 0, weights is None (caller uses fixed weights).

---

## 2. News Alpha Strategies

**Module:** `src.signals.news_engine`  
**Input:** `data/news/{ticker}_news.json` (headlines/bodies). **Sentiment:** FinBERT (ProsusAI/finbert). **Events:** spacy `en_core_web_md` + EventDetector. **Deduplication:** Levenshtein fuzzy match on headlines (ratio &gt; 0.85 = duplicate) to prevent double-counting across DualStream (Marketaux + Tiingo). **Overlay:** `news_weight` (e.g. 0.20) in config; **Final_Score = 0.8 × Technical_Score + 0.2 × News_Composite**.

### 2.1 Strategy A: News Momentum (Rising/Falling Buzz)

- **Logic:** Z-score of article volume (rolling 24h count) from existing JSON feeds; 20-day mean and std.
- **Signal:** **Buzz Multiplier** active when current count &gt; 2σ above the 20-day mean.
- **Use:** Normalized buzz ratio and multiplier flag feed into news_composite; backtest can log News Buzz T/F.

### 2.2 Strategy B: News Surprise (Sentiment Delta)

- **Signal:** High positive surprise acts as a leading indicator for technical breakouts.
- **Warm-up:** 30 days of news to build baseline. **Cold start:** &lt; 30 days → neutral (0.5).

### 2.3 Strategy C: Cross-Sectional (Sector Relative)

- **Signal:** Ticker receives a bonus if in top 10% of its sector by sentiment, even if absolute sentiment is neutral.

### 2.4 Strategy D: Event-Driven (Catalyst Tracking)

- **Logic:** EventDetector (spacy NER + phrase matching) flags **Earnings**, **M&A**, **Lawsuit**, **FDA**, and high-impact phrases (e.g. "Earnings Announcement", "CEO Change").
- **Signal:** If a **High Impact** event is detected, assign a **Priority Weight** to that ticker for the next **48 hours**, overriding technical "choppiness" filters.

### 2.5 Composite and Overlay

- **news_composite:** Combination of A–D (e.g. average of normalized buzz, surprise, sector_top10, event_priority), output in [0, 1].
- **Master Score overlay:** `compute_signal_strength(..., news_composite=value)`; when `news_weight` &gt; 0, **final score = 0.8 × technical_master + 0.2 × news_composite** (config `news_weight: 0.20`). Backtest: pass `--news-dir` to enable; `[STATE]` shows News Buzz T/F when news active.
- **Legacy composite (test_signals / run_weekly_rebalance):** Still available: `combined_score = w_supply_chain * supply_chain_score + w_sentiment * sentiment_norm + ...` from `config/signal_weights.yaml`. FinBERT is used for bulk backtesting; Gemini reserved for "Deep Dives" on top tickers.

---

## 3. Portfolio Construction

- **Selection:** Rank by (Master Score or combined score); select top N.
- **Weighting (Master Score backtest):** Inverse volatility (ATR_norm from Signal Day − 1); weights sum to 1 over selected names.
- **Weighting (legacy/combined):** Proportional (score / total_score) or equal (1/N). No position limits in legacy path.

---

## 4. Performance Metrics

- **Sharpe:** `(mean(portfolio_returns) * 252) / (std(portfolio_returns) * sqrt(252))`.
- **Total return:** `cumulative.iloc[-1] - 1` where `cumulative = (1 + portfolio_returns).cumprod()`.
- **Max drawdown:** `(cumulative - cumulative.expanding().max()) / cumulative.expanding().max()`; report minimum.

---

## 5. Dependencies

- `pandas_ta` for all indicator math.
- `PyYAML` for `config/technical_master_score.yaml`.

**Dynamic weighting and regime (formal engines):**
- **PyPortfolioOpt** — rolling mode: EfficientFrontier (max_sharpe) or HRPOpt (Hierarchical Risk Parity) for category weights from historical performance.
- **hmmlearn** — regime mode: **Gaussian HMM (3 states)** for BULL/BEAR/SIDEWAYS from SPY returns; transition matrix from fitted model; fallback SPY vs 200-SMA.
- **Scikit-Learn** — ML mode: Random Forest Regressor with TimeSeriesSplit cross-validation for feature-importance-based category weights.

**News Alpha (formal engines):**
- **transformers + ProsusAI/finbert** — sentiment on headlines/bodies from `data/news/{ticker}_news.json`.
- **spacy (en_core_web_md)** — EventDetector: NER + phrase matching for Earnings, M&A, Lawsuit, FDA, high-impact phrases. Run `python -m spacy download en_core_web_md` after installing spacy.
- **Levenshtein** — headline fuzzy matching to deduplicate DualStream (Marketaux + Tiingo) articles.

No custom optimization or ML math from scratch; normalization uses bounded = static formulas, unbounded = rolling min-max (no sklearn for normalization).
