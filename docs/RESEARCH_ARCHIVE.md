# RESEARCH ARCHIVE — ML Integration Decisions
**System:** AI Supply Chain Trading System
**Date Written:** 2026-02-22
**Author:** Quant Architecture Review
**Status:** Authoritative — do not edit without ADR entry in DECISIONS.md

---

## 1. Architecture Overview

The live signal stack blends three independent alpha sources:

Price CSVs
    ↓
Technical Master Score          (Trend 40% / Momentum 30% / Volume 20% / Vol 10%)
    +
FinBERT News Engine             (sentiment score per ticker, lru_cache)
    +
Sentiment Propagator            (supply chain cascade from hub tickers)
    ↓
Baseline Score  (range: 0–1)
    ↓
Ridge ML Model  (7 features → Z-scored predicted return → sigmoid → 0–1 ML Score)
    ↓
Final = 0.7 × Baseline + 0.3 × ML_Score
    +
Gemini LLM Gate                 (optional, config-gated via llm.enabled)
    +
Volatility Filter               (top-5% 20d vol → flag / reduce)
    ↓
Volatility-Adjusted Alpha Tilt  (optimizer → last_valid_weights.json)

**Active ML model:** `models/saved/ridge_20260221_230133.pkl`
**Features (7):** `momentum_avg`, `volume_ratio_norm`, `rsi_norm`, `news_supply`, `news_sentiment`, `sentiment_velocity`, `news_spike`
**Training corpus:** 4,319 samples across 47 tickers; EODHD news: 34,477 ticker-days
**Blend weights:** 0.70 Baseline / 0.30 ML (wired in `src/core/target_weight_pipeline.py`)

---

## 2. Key Integration Decisions

### 2.1 Hybrid Blend (not pure ML)

**Decision:** Weight ML score at 30%, baseline signal at 70%.

**Rationale:**
- The Ridge model has a walk-forward mean IC of 0.0202 — above the gate threshold but still low in absolute terms.
- Baseline (Technical Master Score + FinBERT) has 3 years of validated backtest performance: Sharpe +0.34 in 2023, +0.20 in 2024.
- A 30/70 blend preserves the proven baseline while injecting ML's cross-sectional discriminatory power.
- Pure ML would require IC > 0.05 sustained over multiple live quarters before warranting a majority weight.

**Sanity check:** If ML score is bearish (< 0.5) while Baseline is bullish, the blend formula automatically reduces effective position to approximately 0.5× — correct risk-reducing behaviour without a binary gate.

**Source:** `src/core/target_weight_pipeline.py`, lines computing `final_score`.

---

### 2.2 Z-Score + Sigmoid for ML Score Normalization

**Problem:** Ridge regression outputs raw predicted return values (e.g., +0.031, -0.008). These are unbounded and not comparable to the Baseline score range (0–1).

**Solution applied:**
1. Compute cross-sectional Z-score of predicted returns across all tickers on a given date.
2. Pass Z-score through sigmoid: `ml_score = 1 / (1 + exp(-z))`.
3. This maps the ML output to (0, 1), centred at 0.5, preserving relative rank and magnitude.

**Why not min-max normalisation?**
Min-max is highly sensitive to outliers. A single extreme prediction would compress all other scores. Z-score + sigmoid is robust to outliers and preserves the full cross-sectional distribution.

**Why not direct use of raw predicted return as a tilt factor?**
Raw returns are scale-dependent and change with market regime. Normalisation ensures the 0.30 blend coefficient remains stable regardless of the magnitude of current predicted returns.

---

### 2.3 News Features: Neutral Defaults for Pre-2025 Training

**Problem discovered (confirmed 2026-02-21):** The Tiingo News API does not honour `startDate`/`endDate` parameters. All returned articles carry approximately November 2025 publication dates regardless of the requested range. This was confirmed via two full re-backfills with `use_cache=False`.

**Implication:** No reliable historical news signal exists for the 2022–2024 training window.

**Policy adopted:**
- `news_supply = 0.5` (neutral)
- `news_sentiment = 0.5` (neutral)
- For all training rows pre-2025.

**Live inference (2025+):** Marketaux (primary) and Tiingo (secondary) provide real publication-date articles. FinBERT scores are live and valid.

**Impact on model:** The model's non-zero coefficients (`sentiment_velocity -0.0911`, `rsi_norm -0.0765`, `news_sentiment +0.0263`) were learned with neutral news defaults in training — any live news signal is additive alpha not yet fully baked into the model weights. This is a known conservative bias; it will correct naturally as live data accumulates and the model is retrained.

---

### 2.4 Contrarian Sentiment Velocity Signal

**Observation (post-training coefficient inspection):**
- `sentiment_velocity` coefficient: **-0.0911** (strongest non-zero feature)
- Interpretation: declining sentiment predicts positive returns in the AI supply chain universe.

**Hypothesis:** The AI/semiconductor names in this universe are consensus hype targets. When analyst/media sentiment fades on a name, institutional rebalancing often creates a short-term mean-reversion opportunity.

**Portfolio implication (confirmed 2026-02-22 live run):**
- NVDA scored 0.414 despite being the most-discussed AI ticker — penalised by high sentiment velocity.
- TEAM, 6758.T, PATH — quieter names, lower sentiment velocity — scored top-3.
- This is consistent with the contrarian hypothesis.

**Caution:** One live observation is insufficient to validate causality. This should be tracked over ≥ 20 live weeks before drawing conclusions.

---

## 3. Rejected / Unused Strategies

### 3.1 Cross-Sectional Percentile Ranking

**What it is:** Convert each ticker's score to its rank percentile across the universe (0–1). Assign weights proportional to percentile rank.

**Why rejected:**
- Percentile ranking destroys magnitude information. A score of 0.95 and 0.51 both receive "high rank" if the distribution is concentrated. The Ridge model's ability to discriminate between confident and marginal picks is lost.
- In a universe where most scores cluster between 0.48–0.65, percentile expansion creates false precision and over-weights marginal names.

**When it would be appropriate:** If the score distribution is consistently bimodal (clear winners vs. losers), percentile ranking would be stable. Not the case here with 47 tickers and a 0.30 ML blend.

---

### 3.2 Hard Gate Binary Filter

**What it is:** Apply a fixed minimum score threshold (e.g., score ≥ 0.60) as a binary gate. Tickers below the gate receive zero weight regardless of rank.

**Why not primary:**
- With a fixed 0.60 threshold on the current model, only 1–3 tickers qualify in most weeks (confirmed: only TEAM qualified at 0.658 on 2026-02-22). Severe concentration risk.
- Threshold would require manual recalibration as the score distribution shifts with market regime.

**Backup use case:** The hard gate logic is appropriate as a secondary volatility-regime filter — e.g., in a confirmed BEAR regime (SPY < 200 SMA), raise the effective gate to 0.65 to force cash-holding when conviction is low. Not yet implemented; flagged for Phase 4.

---

### 3.3 Mean-Variance Optimisation (MVO / Markowitz)

**Why researched:** MVO is theoretically optimal for maximising Sharpe given expected returns and covariance.

**Why rejected for this system:**
1. **Covariance instability:** With 47 tickers and weekly rebalance, the estimated covariance matrix is rank-deficient and numerically unstable without heavy regularisation (shrinkage).
2. **Expected return sensitivity:** MVO solutions are notoriously sensitive to small errors in expected return inputs. The Ridge model's IC of 0.02 introduces substantial estimation error — MVO would amplify rather than dampen this noise.
3. **Concentration:** Unconstrained MVO frequently produces extreme corner solutions (100% in 1–2 tickers). Constraints required to make it practical are equivalent in complexity to the simpler Volatility-Adjusted Alpha Tilt.

**When appropriate:** MVO becomes viable when IC > 0.10 sustained over 50+ observations and a stable covariance estimate is available (requires daily rebalance or 2+ years of live returns).

---

### 3.4 Hierarchical Risk Parity (HRP)

**Why researched:** HRP (López de Prado, 2016) is robust to covariance instability and avoids matrix inversion. Popular in institutional quant funds.

**Why rejected:**
- HRP is a pure risk-parity method — it ignores the alpha signal (ML score) entirely.
- In this system, the alpha signal (ML score via Ridge) is the primary edge. An allocation method that ignores it defeats the purpose of building the ML layer.
- HRP would be appropriate only as a risk budget overlay after alpha-tilt weighting — a Phase 4 enhancement if drawdown control becomes insufficient.

---

## 4. Adopted Strategy: Volatility-Adjusted Alpha Tilt

**Method:**

raw_weight[t] = score[t] / vol_20d[t]
effective_threshold = max(np.quantile(all_scores, top_quantile=0.75), score_floor=0.50)
eligible = {t : score[t] >= effective_threshold}
raw_weight[t] = 0 for t not in eligible
Normalise: weight[t] = raw_weight[t] / Σ raw_weight
Cap: weight[t] = min(weight[t], max_weight=0.25), redistribute excess iteratively

**Parameters (config: `scripts/portfolio_optimizer.py`):**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `top_quantile` | 0.75 | Top 25% of universe always eligible (~10–12 tickers at 47 tickers) |
| `score_floor` | 0.50 | Absolute minimum — never include sub-neutral scores |
| `max_weight` | 0.25 | Hard cap; prevents single-name concentration > 25% |
| `vol_window` | 30 days | Stable vol estimate; shorter windows too noisy weekly |

**Why this method:**
- Retains full magnitude of the alpha signal (unlike percentile ranking)
- Naturally down-weights high-volatility names without binary exclusion (unlike hard gate)
- No covariance matrix required (unlike MVO)
- Produces 5–12 positions dynamically based on score distribution (unlike fixed top-N)
- Computationally trivial (sub-second on 47 tickers)

**Live output (2026-02-22):**
6758.T   21.9%   score 0.545 / vol 0.370
MSFT     17.1%   score 0.536 / vol 0.484
SNPS     13.9%   score 0.575 / vol 0.574
TEAM     13.4%   score 0.658 / vol 0.626
PLTR     11.4%   score 0.520 / vol 0.707
PATH     11.3%   score 0.542 / vol 0.571
ORCL     10.9%   score 0.549 / vol 0.611

**Outputs written:** `outputs/last_valid_weights.json`, `outputs/last_optimized_weights.json`

---

## 5. Validation Standards

### 5.1 IC Gate (ML model admission criterion)

- **Method:** Anchored walk-forward cross-validation (expanding window)
- **Folds:** 4 (each fold adds one year of data)
- **Metric:** Pearson IC (Information Coefficient) = correlation of predicted vs. realised 1-week returns
- **Gate threshold:** Mean IC ≥ 0.02
- **Result (2026-02-21):** Mean IC = 0.0202. Fold ICs: 0.0314, 0.0551, 0.0070, -0.0129. **PASSED.**

**Interpretation:** IC of 0.02 is modest by institutional standards (typical edge: 0.05–0.15) but statistically above noise for a 4319-sample training set with predominantly neutral news features. The model earns its 30% blend weight.

**Retraining trigger:** Retrain and re-gate if: (a) live IC falls below 0.01 over 10+ weeks, (b) feature distribution shifts materially (e.g., news data source changes), or (c) universe composition changes by > 10 tickers.

---

### 5.2 Live IC Tracking

`scripts/generate_performance_report.py` computes live Pearson and Spearman IC from `outputs/trading.db → forward_returns (1d)` vs `signals.score`. Minimum 5 observations required for reporting; meaningful inference requires ≥ 20.

**Current status:** 0 observations (system went live 2026-02-22). First meaningful IC measurement expected ~2026-03-14 (15 trading days).

---

### 5.3 Backtest Baselines (pre-ML, validated)

| Year | Sharpe | Return | Max Drawdown | Notes |
|------|--------|--------|--------------|-------|
| 2022 | -0.2759 | -17.95% | -20.65% | Broad tech bear; SPY -19% |
| 2023 | +0.3399 | +78.10% | -19.93% | NVDA/AMD news active |
| 2024 | +0.1985 | +33.88% | -10.31% | vs S&P ~25%, NASDAQ ~29% |

These are pre-ML baseline results (Technical + FinBERT only). ML blend expected to modestly improve Sharpe and reduce drawdown as live IC accumulates.

---

## 6. Implementation Notes

### 6.1 `news_weight` vs `ml_weight` in target_weight_pipeline.py

The file `src/core/target_weight_pipeline.py` contains two distinct weighting parameters that are easy to confuse:

| Parameter | What it controls | Current value |
|-----------|-----------------|---------------|
| `news_weight` | Weight of FinBERT news score within the **Baseline** signal composition | Configured in `config/strategy_params.yaml` |
| `ml_weight` | Weight of ML Score in the **final blend** (`Final = (1-ml_weight) × Baseline + ml_weight × ML_Score`) | 0.30 (hardcoded in pipeline) |

These operate at different levels of the signal stack. `news_weight` is internal to the Baseline calculation. `ml_weight` is the outer blend coefficient. Changing `news_weight` does not change the ML contribution.

### 6.2 Stale Model Guard

`config/model_config.yaml → training.model_path` points to the active model pkl. Two stale models exist in `models/saved/`:
- `ridge_20260221_131840.pkl` — 5 features, do not load
- `ridge_20260221_123540.pkl` — 5 features, do not load

The active model (`ridge_20260221_230133.pkl`) has 7 features. Loading a 5-feature model against a 7-feature feature matrix will raise a `ValueError` at inference time. The model_config.yaml path is the single source of truth — never load by filename directly.

### 6.3 Sentiment Propagator Interaction

`src/signals/sentiment_propagator.py` cascades sentiment scores from hub tickers (NVDA, TSMC, etc.) to downstream supply chain tickers. This runs inside the Baseline calculation, before ML blending. The ML model sees the post-propagation `news_sentiment` value as its input feature — meaning the propagator's output is already embedded in the ML feature vector. This is intentional: the ML model learns the *residual* return after propagation-adjusted sentiment.

---

## 7. Future Research Directions

| Direction | Priority | Pre-requisite |
|-----------|----------|---------------|
| Retrain model on live returns (2025+) with real news scores | High | 6+ months of live signals |
| Test non-linear models (XGBoost, LightGBM) | Medium | IC validation on current Ridge first |
| HRP as risk-budget overlay on top of alpha tilt | Medium | 20+ weeks of drawdown data |
| Hard Gate for BEAR regime (SPY < 200 SMA) | Medium | Regime detection re-wiring |
| Real-time intraday features (order flow imbalance) | Low | Real-time data feed required |
| Monte Carlo significance testing on backtest results | Low | Statistical validation sprint |
